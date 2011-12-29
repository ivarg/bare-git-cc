import re
from util import popen


class GitFacade(object):
    def __init__(self, git_dir):
        self.git_dir = git_dir

    def getTopLog(self, branch=None):
        pass

    def diffsByCommit(self, commitId):
        return self._git_exec(['diff','--name-status', '-M', '-z', '%s^..%s' % (commitId, commitId)])

    def resetHard(self, ref):
        self._git_exec(['reset', '--hard', ref])

    def checkout(self, ref):
        self._git_exec(['checkout', ref])

    def addFile(self, file):
        # ivar: why errors=False?
        self._git_exec(['add', '-f', file], errors=False)

    def removeFile(self, file):
        self._git_exec(['rm', file])

    def pullRebase(self):
        self._git_exec(['pull', '--rebase'])

    def push(self):
        self._git_exec(['push'])

    def commit(self, msg, env=None):
        self._git_exec(['commit', '-m', msg], env=env)

    def listFiles(self):
        return self._git_exec(['ls-files']).strip()

    def branchHead(self, branch='HEAD'):
        return self._git_exec(['show', '-s', '--format=%H', branch]).strip()

    def commitMessage(self, commitId):
        return self._git_exec(['log', '--format=%B', '%s^..%s' % (commitId, commitId)]).strip()

    def authorDate(self, commitId):
        return self._git_exec(['show', '-s', '--format=%ai', commitId])[:19]
        
    def authorName(self, commitId):
        return self._git_exec(['show', '-s', '--format=%an', commitId]).strip()

    def authorEmail(self, commitId):
        return self._git_exec(['show', '-s', '--format=%ae', commitId]).strip()

    def mergeCommitFf(self, commitId, msg):
        self._git_exec(['merge', '--ff', '--commit', '-m', msg, commitId])

    def mergeCommitNoFf(self, commitId, msg):
        self._git_exec(['merge', '--no-ff', '--commit', '-m', msg, commitId])

    def mergeAbort(self):
        self._git_exec(['merge', '--abort'])

    def commitHistoryPathBlob(self, fromRef, toRef):
        # ivar: explore the need for x01 delimiters when using the -z flag
        return self._git_exec(['log', '-z', '--first-parent', '--reverse', '--format=%x01%H%x02%s%x02%b', '%s..%s' % (fromRef, toRef)]).strip('\x01')

    def reverseCommitHistoryList(self, fromRef, toRef='HEAD'):
        '''
        Return a reversed list of commit ids in the given range, i.e. in the order they were created.
        '''
        # ivar: why not use -z flag here?   
        commits = self._git_exec(['log', '--first-parent', '--reverse', '--format=%H', '%s..%s' % (fromRef, toRef)]).strip()
        return commits.split('\n')


    def _git_exec(self, cmd, **args):
        return popen('git', cmd, self.git_dir, **args)

