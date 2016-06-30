'''
Command line 'lminfo' tool.
'''

import argparse
import os
import sys
import textwrap

from lminfo import ParseFlexlm


class FlexlmError(Exception):
    pass


class App(object):
    '''
    Application object, implements a command-line application for the
    'lminfo' command.
    '''

    def parse_args(self):
        '''
        Parse command line arguments, setup and provide --help text
        '''
        desc = """\
        This tool gets Flexlm license usage data, and prints it out in a human-
        and/or machine-readable format.
        """
        desc = textwrap.dedent(desc)

        #epilog = """\
        #    Some extra text to go after the options help (usually examples)
        #"""
        #epilog = textwrap.dedent(epilog)

        parser = argparse.ArgumentParser(
                 description=desc,
                 #epilog=epilog,
                 formatter_class=argparse.RawDescriptionHelpFormatter)

        def paa(*name, **otherargs):
            '''Wraps add_argument, allows ---opt shorthand for -opt and --opt'''
            sad_opts = [x.replace('---','-') for x in name if x.startswith('---')]
            sd2_opts = ['-'+x for x in sad_opts]
            reg_opts = [x for x in name if not x.startswith('---')]
            names = reg_opts + sd2_opts + sad_opts
            parser.add_argument(*names, **otherargs)

        paa('---licfile', help='license file to use')

        of_choices = ('json', 'text', 'summary', 'details')
        paa('---output', nargs='?', default='json', choices=of_choices,
            help='one of %s' % (', '.join(of_choices)))

        paa('---verbose', action='store_true', default=False,
            help='print flexlm command that gets raw data')

        return parser.parse_args()


    def run(self):
        '''
        Implements lminfo command to print AWS configs and/or run commands.
        '''
        args = self.parse_args()

        flexlmp = ParseFlexlm(
                      licfile=args.licfile,
                      output=args.output,
                      verbose=args.verbose,
                  )
        print flexlmp.get_license_info()
        sys.exit(0)


    def main(self):
        '''
        Runs the application, catches exceptions and returns exit status
        '''
        try:
            self.run()
        except (FlexlmError), err:
            print "lminfo: error, %s" % err
            sys.exit(1)


if __name__ == '__main__':
    myapp = App()
    myapp.main()


SQOR-0004:lminfo jeremyyabrow$ 
