import re
from datetime import datetime
import util
import logging
import os.path
import os

logger = logging.getLogger('log.bgcc.file')


def formatRecord(res, *args):
    xx = '(%s, \'%s\'),' % (str(args), str(res))
    return xx


class GitFacade(object):
    def __init__(self, git_dir):
        self.git_dir = os.path.abspath(git_dir)
        if not os.path.exists(self.git_dir):
            os.makedirs(self.git_dir)

    def init(self):
        self._git_exec(['init'])

    def exists(self):
        return os.path.exists(os.path.join(self.git_dir, '.git'))

    def diffsByCommit(self, commitId):
        diffs = self._git_exec(['diff','--name-status', '-M', '-z', '%s^..%s' % (commitId, commitId)])
        return diffs

    def resetHard(self, ref):
        self._git_exec(['reset', '--hard', ref])

    def resetBranches(self, branches):
        for branch in branches.keys():
            self.checkout(branch)
            self.resetHard(branches[branch])

    def checkout(self, ref):
        try:
            self._git_exec(['checkout', ref])
        except:
            self._git_exec(['checkout', '-b', ref])

    def addFile(self, file):
        # ivar: why errors=False?
        # we need to add lowercase file names
        self._git_exec(['add', file], errors=True)

    def removeFile(self, file):
        self._git_exec(['rm', file])

    def pullRebase(self):
        self._git_exec(['pull', '--rebase'])

    def push(self):
        self._git_exec(['push'])

    def commit(self, msg, env=None):
        self._git_exec(['commit', '-m', msg], env=env)

    def setTag(self, tagname, ref=''):
        tag = ['tag', '-f', tagname]
        if ref != '': tag.append(ref)
        self._git_exec(tag)

    def removeTag(self, tagname):
        self._git_exec(['tag', '-d', tagname])

    def filesList(self):
        res = self._git_exec(['ls-files']).strip().split('\n')
        return res

    def branchHead(self, branch='HEAD'):
        res = self._git_exec(['show', '-s', '--format=%H', branch]).strip()
        return res

    def updateRemote(self):
        self._git_exec(['remote', 'update'])

    def commitMessage(self, commitId):
        # res = self._git_exec(['log', '--format=%B', '%s^..%s' % (commitId, commitId)]).strip()
        res = self._git_exec(['show', '-s', '--format=%s', commitId])
        return res

    def commitDate(self, commitId):
        dateStr = self._git_exec(['show', '-s', '--format=%ci', commitId])[:19]
        res = datetime.strptime(dateStr, '%Y-%m-%d %H:%M:%S')
        return res

    def authorName(self, commitId):
        res = self._git_exec(['show', '-s', '--format=%an', commitId]).strip()
        return res

    def authorEmail(self, commitId):
        res = self._git_exec(['show', '-s', '--format=%ae', commitId]).strip()
        return res

    def blob(self, commitId, file):
        sha = self._git_exec(['ls-tree', commitId, file]).split(' ')[2].split('\t')[0]
        blob = self._git_exec(['cat-file', 'blob', sha])
        return blob

    def mergeCommitFf(self, commitId, msg):
        self._git_exec(['merge', '--ff', '--commit', '-m', msg, commitId])

    def mergeCommitNoFf(self, commitId, msg):
        self._git_exec(['merge', '--no-ff', '--commit', '-m', msg, commitId])

    def mergeAbort(self):
        self._git_exec(['merge', '--abort'])

    def commitHistoryPathBlob(self, fromRef, toRef):
        # ivar: explore the need for x01 delimiters when using the -z flag
        res = self._git_exec(['log', '-z', '--first-parent', '--reverse', '--format=%x01%H%x02%s%x02%b', '%s..%s' % (fromRef, toRef)]).strip('\x01')
        return res

    def reverseCommitHistoryList(self, fromRef, toRef='HEAD'):
        '''
        Return a reversed list of commit ids in the given range, i.e. in the order they were created.
        '''
        # ivar: why not use -z flag here?   
        commits = self._git_exec(['log', '--first-parent', '--reverse', '--format=%H', '%s..%s' % (fromRef, toRef)]).strip()
        res = commits.split('\n') if commits != '' else None
        return res

    def push(self):
        cmd = ['push', 'origin', 'master']
        self._git_exec(cmd)


    def _git_exec(self, cmd, **args):
        logger.debug('git %s' % ' '.join(cmd))
        return util.popen('git', cmd, self.git_dir, **args)

