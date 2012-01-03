import re
from datetime import datetime
from util import popen, Loggable
import logging

logger = logging.getLogger()

class GitFacade(Loggable):
    def __init__(self, git_dir):
        self.git_dir = git_dir

    def diffsByCommit(self, commitId):
        self.printSignature(commitId)
        diffs = self._git_exec(['diff','--name-status', '-M', '-z', '%s^..%s' % (commitId, commitId)])
        return diffs

    def resetHard(self, ref):
        self.printSignature(ref)
        self._git_exec(['reset', '--hard', ref])

    def resetBranches(self, branches):
        for branch in branches.keys():
            self.checkout(branch)
            self.resetHard(branches[branch])

    def checkout(self, ref):
        self.printSignature(ref)
        self._git_exec(['checkout', ref])

    def addFile(self, file):
        self.printSignature(file)
        # ivar: why errors=False?
        self._git_exec(['add', '-f', file], errors=False)

    def removeFile(self, file):
        self.printSignature(file)
        self._git_exec(['rm', file])

    def pullRebase(self):
        self.printSignature()
        self._git_exec(['pull', '--rebase'])

    def push(self):
        self.printSignature()
        self._git_exec(['push'])

    def commit(self, msg, env=None):
        self.printSignature(msg)
        self._git_exec(['commit', '-m', msg], env=env)

    def setTag(self, tagname, ref=''):
        self.printSignature(tagname, ref)
        tag = ['tag', '-f', tagname]
        if ref != '': tag.append(ref)
        self._git_exec(tag)

    def removeTag(self, tagname):
        self.printSignature(tagname)
        self._git_exec(['tag', '-d', tagname])

    def filesList(self):
        self.printSignature()
        return self._git_exec(['ls-files']).strip().split('\n')

    def branchHead(self, branch='HEAD'):
        self.printSignature(branch)
        res = self._git_exec(['show', '-s', '--format=%H', branch]).strip()
        return res

    def commitMessage(self, commitId):
        self.printSignature(commitId)
        res = self._git_exec(['log', '--format=%B', '%s^..%s' % (commitId, commitId)]).strip()
        return res


    def authorDate(self, commitId):
        self.printSignature(commitId)
        res = datetime.strptime(self.authorDateStr(commitId), '%Y-%m-%d %H:%M:%S')
        return res
        
    def authorDateStr(self, commitId):
        self.printSignature(commitId)
        res = self._git_exec(['show', '-s', '--format=%ai', commitId])[:19]
        return res

    def authorName(self, commitId):
        self.printSignature(commitId)
        res = self._git_exec(['show', '-s', '--format=%an', commitId]).strip()
        return res

    def authorEmail(self, commitId):
        self.printSignature(commitId)
        res = self._git_exec(['show', '-s', '--format=%ae', commitId]).strip()
        return res

    def blob(self, commitId, file):
        sha = self._git_exec(['ls-tree', commitId, file]).split(' ')[2].split('\t')[0]
        return self._git_exec(['cat-file', 'blob', sha])

    def mergeCommitFf(self, commitId, msg):
        self.printSignature(commitId, msg)
        self._git_exec(['merge', '--ff', '--commit', '-m', msg, commitId])

    def mergeCommitNoFf(self, commitId, msg):
        self.printSignature(commitId, msg)
        self._git_exec(['merge', '--no-ff', '--commit', '-m', msg, commitId])

    def mergeAbort(self):
        self.printSignature()
        self._git_exec(['merge', '--abort'])

    def commitHistoryPathBlob(self, fromRef, toRef):
        self.printSignature(fromRef, toRef)
        # ivar: explore the need for x01 delimiters when using the -z flag
        res = self._git_exec(['log', '-z', '--first-parent', '--reverse', '--format=%x01%H%x02%s%x02%b', '%s..%s' % (fromRef, toRef)]).strip('\x01')
        logger.debug(res)
        return res

    def reverseCommitHistoryList(self, fromRef, toRef='HEAD'):
        '''
        Return a reversed list of commit ids in the given range, i.e. in the order they were created.
        '''
        self.printSignature(fromRef, toRef)
        # ivar: why not use -z flag here?   
        commits = self._git_exec(['log', '--first-parent', '--reverse', '--format=%H', '%s..%s' % (fromRef, toRef)]).strip()
        res = commits.split('\n') if commits != '' else None
        logger.debug(res)
        return res


    def _git_exec(self, cmd, **args):
        return popen('git', cmd, self.git_dir, **args)

