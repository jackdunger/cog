'''A task that looks for Doxygen warnings. A single warning triggers a failure'''

import os
import subprocess
import cog.task

# Sub directories that must be Doxygenated (for help output)
doxy_dirs = ["src/du","src/ds"]

class DoxyCheck(cog.task.Task):
    '''
    Grab the Doxygen Log, and fail if there are warnings
    '''        
    def __init__(self, *args):
        cog.task.Task.__init__(self, *args)

    def run(self, document, work_dir):
        '''Run the task.

        :param document: Task document from the database
        :param work_dir: Temporary working directory
        '''
        kwargs = document.get('kwargs', {})
        sha = kwargs.get('sha', None)
        git_url = kwargs.get('git_url', None)
        base_repo_ref = kwargs.get('base_repo_ref', None)
        base_repo_url = kwargs.get('base_repo_url', None)

        if sha is None:
            return {'success': False, 'reason': 'missing revision id'}
        if git_url is None:
            return {'success': False, 'reason': 'missing git url'}
        if (base_repo_url and base_repo_ref is None or
                base_repo_ref and base_repo_url is None):
            return {'success': False,
                    'reason': 'incomplete base specification for merge'}

        # get the new pull request
        code = cog.task.git_clone(git_url, sha, sha, work_dir=work_dir)
        if code is None or (code != 0 and code != 1):
            return {'success': False, 'reason': 'git clone failed',
                    'code': str(code)}

        # Get doxy log
        rat_dir = os.join(work_dir,sha) if work_dir else sha
        doxy_log = self.get_doxy_log(rat_dir)

        # pass if no warnings, print log to HTML
        if doxy_log is None:
            return {'success': False, 'reason': "could not get doxy log"}
        
        web_page = self.print_HTML(doxy_log,"doxy_check.html")
        attachment = {"filename" : "doxycheck.html", "contents": web_page, "link_name": "doxycheck"}
        success = (doxy_log.count("warning:") == 0)
        return {'success': success, "attachments":[attachment]}

    def get_doxy_log(self,rat_dir):
        ''' 
        Get the Doxygen log. Must be run inside rat directory. doxyfile exists only after scons - 
        but doxyfile-in is missing only the rat version and exists from clone
        :param doxyfile_path relative or abs path to doxyfile to run
        :returns: doxygen make log as a string, none if fails 
        '''
        doxyfile = os.path.join("dox","doxyfile-in")
        cmd = "cd %s && doxygen %s" %(rat_dir,doxyfile)
        try:
            doxy_log = cog.task.system_output(cmd)
            return doxy_log
        except subprocess.CalledProcessError as exc:
            print "Error grabbing Doxygen log:"
            print exc.output
            return None


    def print_HTML(self,log_string,out_file):
        '''
        Write HTML file results to file and return as string
        :param doxygen log
        :returns: doxygen log HTML as string
        '''
        n_warnings  = log_string.count("warning:")
        test_passed = (n_warnings == 0)
        web_page = """
        <html>   
        <head>
        <title> Doxygen Warning Checker </title>
        </head>
        <body>
        <h1> Doxygen Warning Checker </h1>
        <h2 style="color: %s"> Test %s </h2>
        """ %("green" if test_passed else "red",
              "PASSED" if test_passed else "FAILED with %s warnings" %n_warnings)

        if not test_passed:
            web_page += "<p>Headers in %s need Doxygen tags -- docDB-1018</p>" %(", ".join(doxy_dirs))
            web_page += """
            <h2> Doxygen Log:</h2>
            <p> %s </p>
            """ %(log_string)
            web_page += """
            </body>
            </html>
            """
        with open(out_file,"w") as f:
            f.write(web_page)
        return web_page

    
if __name__ == '__main__':
    import sys
    task = DoxyCheck(*(sys.argv[1:]))
    task()
