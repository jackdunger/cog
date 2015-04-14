'''Structures and helper utilities for tasks.'''

import os
import time
import socket
import subprocess
import tempfile
import shutil
import cog.db

class Task(object):
    '''Scaffolding for defining tasks.

    Tasks read a task document from the database, run some code, and post
    results.

    :param host: CouchDB hostname
    :param dbname: CouchDB database name
    :param username: Database username
    :param password: Database password
    :param doc_id: Document ID of the task to run
    '''
    def __init__(self, host, dbname, username, password, doc_id):
        self.couchdb = cog.db.CouchDB(host, dbname, username, password)
        self.database = self.couchdb.database
        self.document = self.database[doc_id]
        self.work_dir = tempfile.mkdtemp()  # working directory

    def __call__(self, clone=True, build=True):
        '''Run the task and update the database.'''
        self.start()
        try:
            results = self.run(self.document, self.work_dir)
        except Exception as e:
            results = {
                'success': False,
                'reason': 'Unhandled exception in task: %s' % str(e)
            }
        self.finish(results)

    def __del__(self):
        try:
            shutil.rmtree(self.work_dir)
        except Exception:
            print 'Task.__del__: Error removing temporary working directory'

    def start(self):
        '''Update the database to indicate that the task has started.'''
        self.document['started'] = time.time()
        self.document['node'] = socket.getfqdn()
        self.database.save(self.document)
        self.document = self.database[self.document.id]

    def finish(self, results):
        '''Update the database with results when task is finished.

        :param results: Dictionary of task results
        '''
        # upload attachments
        if 'attachments' in results:
            for attachment in results['attachments']:
                self.database.put_attachment(self.document,
                                             attachment['contents'],
                                             filename=attachment['filename'])
            self.document = self.database[self.document.id]

        self.document['results'] = results

        if 'attachments' in results:
            for attachment in results['attachments']:
                # if a link name is specified, put a link next to results on the
                # web page
                if 'link_name' in attachment:
                    self.document['results'].setdefault('attach_links', []).append({
                        'id': attachment['filename'],
                        'name': attachment['link_name']
                    })
            del self.document['results']['attachments']
            self.database.save(self.document)
            self.document = self.database[self.document.id]
        
        self.document['results'] = results
        self.document['completed'] = time.time()
        self.database.save(self.document)

    def run(self, document, work_dir):
        '''Override this method to define task code.

        :param document: Document defining the task to run
        :param work_dir: Working directory
        '''
        raise Exception('Task.run: Cannot call run method on base class')


def system(cmd, work_dir=None):
    '''Call a function in the shell.

    A wrapper for subprocess.call. Requires the bash shell.

    :param cmd: The command string
    :param work_dir: The working directory in which to execute
    :returns: The integer return code of the system call
    '''
    if work_dir:
        cmd = ('cd %s && ' % work_dir) + cmd

    print cmd
    return subprocess.call([cmd], executable='/bin/bash', shell=True)


def system_output(cmd, work_dir=None):
    '''Call a function in the shell and grab stdout & stderr 

    A wrapper for subprocess.check_output. Requires the bash shell.

    :param cmd: The command string
    :param work_dir: The working directory in which to execute
    :returns: stdout and stderr of the process as string
    :raises subprocess.CalledProcessError
    '''
    if work_dir:
        cmd = ('cd %s && ' % work_dir) + cmd
    print cmd
    return subprocess.check_output([cmd], stderr=subprocess.STDOUT, executable='/bin/bash', shell=True)


def git_clone(url, sha, target=None, work_dir=None):
    '''Clone a git repository.

    The arguments are parsed as::

        cd [work_dir] && git clone [url] [target] && git checkout [sha]

    You may need to set up SSH keys if authentication is needed.

    :param url: The URL to git clone
    :param sha: The SHA of the revision to check out
    :param target: Name of directory to clone into
    :param work_dir: Working directory in which to perform clone
    :returns: Return code of "git clone"
    '''
    if target is None:
        target = sha

    if work_dir:
        target = os.path.join(work_dir, target)

    target = os.path.abspath(target)

    if not os.path.exists(target):
        cmd = ' '.join(['git clone', url, target, '&& cd %s && ' % target,
                       'git checkout', sha, '&> /dev/null'])
        return system(cmd)
    else:
        return None

def git_fetch(url,repo_dir):
    '''Fetch a remote, commands executed in repository directory (usually not = work_dir)
    :param url: The URL to git fetch
    :param repo_dir: directory containing git repository
    :returns: Return code of "git fetch"
    '''
    cmd = ' '.join(['git remote add fork',url])
    system(cmd,repo_dir)
    cmd = 'git fetch fork'
    return system(cmd,repo_dir)
    

def git_merge(url, ref, work_dir=None):
    '''Merge a remote ref into an existing local clone.

    This will perform:

        git remote add fork [url]
        git pull fork [ref]

    You may need to set up SSH keys if authentication is needed.

    :param url: URL of the remote
    :param ref: Name of remote ref to pull
    :param work_dir: Working directory
    :returns: Return code of "git pull"
    '''
    cmd = ' '.join(['git remote add fork', url])
    system(cmd, work_dir)

    cmd = ' '.join(['git pull fork', ref, '&> /dev/null'])

    return system(cmd, work_dir)

def get_changed_files(sha,repo_dir):
    '''Get a list of files changed in the fetched code using git diff. (remote must be fetched)
    "..." gives only changes new in sha relative to local
    :param sha: sha of fork to test
    :returns: list of file paths relative to rat dir
    '''
    cmd = "git diff --name-only ...%s" %(sha)
    changed_files = system_output(cmd,repo_dir).splitlines()
    return changed_files
    
def get_diff(file,sha,repo_dir):
    ''' Get the diff for a file for a given sha. (remote must be fetched) 
    "..." gives only changes new in sha relative to local
    :param sha: name of remote ref to test
    :param file: path to modified file
    :param repo_dir: path to repository directory
    :returns: git diff as a string
    '''
    # check file exists in the repo already
    if os.path.isfile(file):
        cmd = "git diff -U0 ...%s %s" %(sha,file)
        return system_output(cmd,repo_dir)
    # otherwise need to add the file 
    else:
        cmd = "git checkout %s %s" %(sha,file)
        system(cmd,repo_dir)
        cmd = "git diff -U0 ...%s %s" %(sha,file)
        return system_output(cmd,repo_dir)
    
def scons_build(work_dir, options=None, configure=True,
        configure_options=None):
    '''Compile with scons.

    Note: Returns (None, None) if configure runs and fails.

    :param work_dir: Working directory
    :param options: Options to pass to scons
    :param configure: If True, run "./configure" first
    :param configure_options: Options to pass to configure
    :returns: Tuple with (return code of "scons", text of log)
    '''
    if options is None:
        options = ['-j2']

    if configure_options is None:
        configure_options = []

    if configure:
        system('./configure %s' % ' '.join(configure_options), work_dir)

    env_file = os.path.join(work_dir, 'env.sh')

    if not os.path.exists(env_file):
        print 'scons_build: ./configure failed (no env.sh file)'
        return None, None

    arglist = (env_file, ' '.join(options))
    ret = system('source %s && scons %s &> build_log.txt' % arglist, work_dir)

    log_text = None
    with open('%s/build_log.txt' % work_dir, 'r') as log_file:
        log_text = log_file.read()

    return ret, log_text

