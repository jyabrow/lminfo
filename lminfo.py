'''
Module to implement Flexlm Parser.
'''

import json
import os
import re
import sys
import time

class FlexlmError(Exception):
    ''' Minimal class to distinguish "expected" vs "unexpected" exceptions '''
    pass

class ParseFlexlm(object):

    '''
    This class implements a Flexlm license data parser. Flexlm has a single
    utility to manage and introspect license data and usage, which dumps data
    as text, but in a non-machine-readable and barely-human-readable format.
    The parser converts this into a well-structured json block.
    '''

    def __init__(self, licfile='./flexlm.lic', output='json', verbose=True):

        self.licfile = licfile
        self.output = output        # Values: 'json', 'text', 'summary', 'details'
        self.verbose = verbose

        self.lminfo = {}            # Dict to store license info by 'feature name'
        self.error = False
        self.error_msg = ""


    def get_license_info(self, licfile=None):
        '''
        Gets license and usage data from Flexlm server, and returns machine-
        readable json data block.
        '''
        if licfile is None:
            licfile = self.licfile
        raw_text = self._get_raw_license_text(licfile)
        (raw_sum, raw_det) = self._preprocess(raw_text)
        self._process_summary(raw_sum)
        self._process_details(raw_det)
        return json.dumps(self.lminfo, indent=4)


    def _get_raw_license_text(self, licfile):
        '''
        Runs the 'lmutil lmstat' command to query the license server, and
        returns the resulting raw text data from stdout.
        '''
        cmd = './lmutil lmstat -c %s -a -i 2>&1' % (licfile)
        # NOTE: '2>&1' gets stderr output in bash and cmd.exe shells

        if self.verbose:
            print >> sys.stderr, "running command: %s" % cmd
        pipe = os.popen(cmd)
        data = pipe.read()
        stat = pipe.close()
        if stat:
            self.error = True
            self.error_msg = stat
            return ""
        else:
            return data


    def _preprocess(self, raw_text):
        '''
        Performs preprocess on raw text data, splits text lines into 'summary',
        and 'details' sections.  The summary section must be parsed first, but
        appears at the end of the 'lmutil lmstat' output.  Summary contains
        data for all licenses whereas the details section only has data for
        licenses being used.

        Returns (summary, details) tuple of text lines.
        '''

        # Implement simple linear state machine to parse flexlm data sections
        # states are: init -> feature_usage_info -> feature_summary_info
        #
        current_state = "init"
        summary_lines = []        # License feature summary text lines
        details_lines = []        # License feature details text lines

        for line in raw_text.split("\n"):

            line = line.strip(' \t')
            words = re.split(r'\s+', line)

            if current_state == "init":

                if line == "Feature usage info:":
                    current_state = "feature_usage_info"

            elif current_state == "feature_usage_info":

                if words == "Feature Version #licenses Expires Vendor".split():
                    current_state = "feature_summary_header"
                else:
                    details_lines.append(line)

            elif current_state == "feature_summary_header":

                if words == "_______ _________ _________ __________ ______".split():
                    #NOTE: this conditional is not future-proof (there have been
                    #      changes in the separator line between versions).
                    current_state = "feature_summary_info"

            elif current_state == 'feature_summary_info':

                # NOTE: "lmutil lmstat" sometimes gives duplicate data sets (reason unknown)
                #       so, if a new section is encountered, quit parsing
                #
                if words[0:3] == "License server status:".split():
                    break

                summary_lines.append(line)

        return (summary_lines, details_lines)


    def _process_summary(self, raw_sum):
        '''
        Processes summary raw text data, extracting the fields listed below for
        each Flexlm license 'feature'.

        Returns None, but:
            Initializes self.lminfo as a list of dict, each element containing
            the following key/values: feature, version, ntotal, nused=0,
            expires, vendor, usage=[].
        '''
        for line in raw_sum:

            words = re.split(r'\s+', line)

            # Looking for lines like:
            # "85527MAYA_F 1.000 5 1-jan-2015 adskflex"

            if len(words) == 5:

                feature_name = words[0]
                version = words[1]
                ntotal = int(words[2])
                expires = convert_expiration_date(words[3])
                vendor = words[4]

                feature_uniq = feature_name + "_" + version

                # HACK ALERT:
                # if feature_uniq already exists, take the earliest expiration
                # date, add the ntotals.  This will help get the right total in
                # the case that there are additional feature entries with the
                # same name and version number, but which have a different
                # expiration date. We combine them because flexlm's usage info
                # doesn't seem to distinguish between such 'overlapping feature-
                # versions'. Sigh.

                if feature_uniq in self.lminfo:

                    self.lminfo[feature_uniq]['ntotal'] += ntotal

                else:
                    self.lminfo[feature_uniq] = dict(
                        feature=feature_name, version=version, ntotal=ntotal,
                        expires=expires, vendor=vendor, nused=0, usage=[],
                        )


    def _process_details(self, raw_det):
        '''
        Processes detailed raw text data, adds usage information to 'lminfo'
        initialized by _process_summary().

        Returns None, but also:
            Adds 'usage' key/value to each element of self.lminfo for which
            usage is found.  The usage value itself is a list of dict, wich
            with each element containing the following key/values: userid,
            host, pid, sw_version, lm_version, start.
        '''

        # Process the details text info, extract per-feature usage info.
        # The text lines appear in a 3-level hierarchy: feature/version/usage

        for line in raw_det:

            words = re.split(r'\s+', line)

            fu_re = r"Users of (\S+):\s+\(Total of (\d+) licenses? issued;  " \
                    r"Total of (\d+) licenses? in use\)"
            match = re.match(fu_re, line)
            if match:

                current_feature = match.group(1)
                #current_total = match.group(2)
                #current_used = match.group(3)
                continue

            # Looking for lines like:
            # "85527MAYAF" v1.000, vendor: adskflex, expiry: 1-jan-0
            if (len(words) == 6) and (words[2] == "vendor:"):

                #redundant_feature_name = words[0]
                current_version = words[1].strip('v,')
                #current_vendor = words[3]

                current_feature_uniq = current_feature + "_" + current_version

                #NOTE: Only needed if summary is missing features,
                #NOTE: does this ever happen?
                if 'usage' not in self.lminfo[current_feature_uniq]:
                    self.lminfo[current_feature_uniq]['usage'] = []
                continue


            #pylint: disable=line-too-long
            # Looking for lines like:
            # "someguy ahost ahost (v1.000) (imdlic01/7111 7581), start Wed 9/12 9:08",
            #
            # or lines like:
            # "titanium titanium.mycompanyslongname.com (v8.500) (imdlic01/7111 7070), start Thu 9/20 17:02",
            # or like:
            # "abaltazar minint-nljd3fo.mycompanyslongnam (v8.500) (imdlic01/7111 14022), start Thu 9/20 16:14"
            #
            # (if machine name is too long, flexlm omits double-print of machine
            # and all subsequent fields are shifted left by 1 position, yuck.

            nwords = len(words)
            if nwords == 9 or nwords == 10:

                userid = words[0]
                host_fullname = words[1]

                # Pull-out relevant pieces of data from usage line word list
                if nwords == 10 and words[6] == 'start':
                    usage_ver = words[3]
                    usage_pid = words[5]
                    usage_date = words[8]
                    usage_time = words[9]
                elif nwords == 9 and words[5] == 'start':
                    usage_ver = words[2]
                    usage_pid = words[4]
                    usage_date = words[7]
                    usage_time = words[8]
                else:
                    continue

                # Apply further string/data-conversions as needed
                host = host_fullname.split('.')[0]    # host.company.com=>host
                ver = usage_ver.strip('()').lstrip('v')     # (v8.500)=>8.500
                pid = usage_pid.rstrip('),')                # 7581),=>7581
                start = flexlm_start_date_to_ts(usage_date, usage_time)

                # Add usage entry to lminfo, maintain used-license count
                usage_entry = dict(userid=userid, host=host, pid=pid,
                                   start=start, sw_version=ver, lm_version=current_version)
                self.lminfo[current_feature_uniq]['usage'].append(usage_entry)
                self.lminfo[current_feature_uniq]['nused'] += 1



####### Global time conversion functions

# NOTE: Hungarian Notation previx for time values & strings, used in the
#       subsequent time-processing functions.
#
# ts = "Time String", human-readable date/time, e.g. "2008-06-10 10:04 (Tue)"
# tv = "Time Value", time value array, e.g. (2008, 6, 10, 10, 5, 53, 1, 162, 1)

def convert_expiration_date(exp_date):
    '''
    Converts Flexlm, PixarAdmin, Sesi expiration date format to the far more
    useful human-readable and machine-sortable 'ts' time string format.
    Accepts "dd-mmm-yyyy" and produces "YYYY-MM-DD HH:MM"
    Example "1-oct-2007" => "2007-10-01 23:59"
    (assumes exact expiration time is midnight on expiration date)
    '''
    try:
        tv_exp = time.strptime(exp_date+" 23:59", "%d-%b-%Y %H:%M")
        ts_out = time.strftime("%Y-%m-%d %H:%M", tv_exp)
    #except ValueError:
    # pylint: disable=broad-except
    #
    except Exception:
        # Explicitly handle case of "1-jan-0" expiration date (FlexLm)
        if (exp_date == "1-jan-0") or (exp_date == "01-jan-0000"):
            ts_out = "9999-12-31 23:59"
        else:
            ts_out = "xxxx-xx-xx xx:xx"
    return ts_out


def flexlm_start_date_to_ts(mmdd, hhmm):
    '''
    Converts Flexlm start date format to the far more useful human-readable and
    machine-sortable 'ts' time string format.

    Accepts "mm/dd hh:mm" and produces "YYYY-MM-DD HH:MM"
    Example "9/13 12:51" => "2007-09-13 12:51"
    '''
    try:
        yyyy = time.strftime("%Y", time.localtime())
        tv_start = time.strptime(mmdd+"/"+yyyy+" "+hhmm, "%m/%d/%Y %H:%M")
        tv_start = adjust_year(tv_start, yyyy)
        ts_out = time.strftime("%Y-%m-%d %H:%M (%a)", tv_start)
    #except ValueError:
    # pylint: disable=broad-except
    except Exception:
        ts_out = "xxxx-xx-xx xx:xx (BAD DATE)"

    return ts_out


def adjust_year(tv_start, yyyy):
    '''
    License manager start dates do not include a year number, so we assume the
    current year. This leads to a potential year rollover problem, e.g. when a
    license is checked out in December but still out in January. We fix it by
    checking if the month > current month, and decrementing the year if needed.
    '''
    tv_adjusted = tv_start
    input_month = time.strftime("%m", tv_start)
    curr_month = time.strftime("%m", time.localtime())
    if input_month > curr_month:
        yyyy -= 1
        tv_adjusted = time.strptime(tv_start+" "+yyyy, "%d-%b-%H:%M %Y")

    return tv_adjusted

