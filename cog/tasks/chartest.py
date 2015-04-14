'''A  task to look for bad ascii chars, missing EOF newlines, tabs and trailing whitespace'''
import subprocess
import os
import cog.task

# Chars that trigger a failure
CRITICAL_CHARS = map(chr,range(0x00,0x09 +1) + range(0x0b,0x1f +1) + [0x7f])
# Only look at files with extensions:
CODE_EXTS     = [".py",".cc",".hh",".h",".c"]

class CharCheck(cog.task.Task):
    '''Check a revision for tab chars, bad ASCII, missing EOF newlines and EOL whitespace
    Clone the master repository, fetch the PR and examine the diff. 
    '''

    def __init__(self,*args):
        cog.task.Task.__init__(self,*args)

    def run(self,document,work_dir):
        '''Run the task.

        :param document: Task document from the database
        :param work_dir: Temporary working directory
        :returns: dict with success key and error lists keyed by changed file
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

        #Clone Master Code 
        code = cog.task.git_clone(base_repo_url, base_repo_ref, base_repo_ref, work_dir=work_dir)
        if code is None or (code != 0 and code != 1):
            return {'success': False, 'reason': 'git clone failed',
                    'code': str(code)}
        #Fetch the fork changes
        repo_dir = base_repo_ref
        if work_dir:
            repo_dir = os.path.join(work_dir,base_repo_ref)
        code = cog.task.git_fetch(git_url,repo_dir)
        if code is None or (code != 0 and code != 1):
            return {'success': False, 'reason': 'git clone failed',
                    'code': str(code)}
        #Find which files have been changed
        changed_files = cog.task.get_changed_files(sha,repo_dir)
        #Only Interested in code files
        changed_code_files = [file for file in changed_files if file.endswith(tuple(CODE_EXTS))]
        #Run a check on each of them
        success = True
        errors  = {}
        for changed_file in changed_code_files:
            diff   = cog.task.get_diff(changed_file,sha,repo_dir)
            file_errors = self.char_check(diff)
            errors[changed_file] = file_errors
            if file_errors != []:
                success = False
        # write web page
        web_page = self.print_HTML(errors,"char_test.html")
        attachments = []
        attachments.append({ 'filename': 'char_test.html',
                             'contents': web_page,
                             'link_name': "CharTest",
                             }) 
        results = {'success':success, 'errors': errors, 'attachments':attachments}
        return results

    def print_HTML(self,errors,out_file):
        ''' Write HTML file results table to file and return as string
        :param errors:  errors dict
        :param out_file: output html path
        '''
        #count number of files failed
        nfails = sum(1 for i in errors.values() if i != [])
        overall_pass = (nfails == 0)
        web_page = '''<html>                                                                  
        <head> 
        <title> White Space and ASCII Checker </title>
        </head>
        <body>
        <h1> White Space and ASCII Checker </h1>
        <h2 style="color: %s"> %s </h2>
        <table border>
        ''' %('green' if overall_pass else 'red', 
              'All Files Passed' if overall_pass else "%i Files Failed" %nfails)
        for filename, error_list in errors.items():
            passed = (error_list == [])
            web_page +=  '''
            <tr> 
            <th> %s </th>    
            <td style="color: %s"> %s </td>
            <td>  %s </td>
            </tr>
           ''' %(filename, 'green' if passed else 'red', 'PASS' if passed else "FAIL",
                 "<br /> ".join(error_list) if not passed else "")
        web_page+= '''                                              
                      </table>
                   </body>
                 </html>                                                                                                 '''
        with open(out_file,"w") as f:
            f.write(web_page)           
        return web_page
 
    def char_check(self,diff):
        ''' Read the diff for a file, find tab chars, bad ASCII chars, trailing whitespace 
        and missing EOF newlines
        :param diff: the diff string
        :returns: a list of errors for the file
        '''
        errors = []
        # Check for git newline warning
        if "\ No newline at end of file" in diff:
            errors.append("No EOF newline")  
        # Get the new lines. Lines beginning "---" in header
        changedLines = [x for x in diff.splitlines() if len(x)!= 0 and x[0] == "+" 
                        and x[:3] != "+++"]
        # Search code lines for trailing whitespace and bad ASCII chars
        for line in changedLines:
            trailingWhiteSpace = len(line) - len(line.rstrip())
            isComment = "//" in line
            if trailingWhiteSpace and not isComment:
                errors.append("%s trailing whitespace chars in line ' %s '" %(trailingWhiteSpace,line))
            for y in CRITICAL_CHARS:
                count = line.count(y)
                if count:
                    error = "%s copies of char %s in line: ' %s'"  %(count,hex(ord(y)),line)
                    if ord(y) == 0x09:
                        error += " => new TAB chars"
                    errors.append(error)
        return errors

if __name__ == '__main__':
    import sys
    task = CharCheck(*(sys.argv[1:]))
    task()
