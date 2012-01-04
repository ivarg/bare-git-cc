import re
from datetime import datetime
import util
import logging

logger = logging.getLogger('bare-git-cc')

# This is temporary stuff just for recording, set level to DEBUG to enable
recorder = logging.getLogger('gitrecorder')
h = logging.FileHandler('gitrecorder.log', 'w')
h.setFormatter(logging.Formatter('%(message)s'))
h.setLevel(logging.INFO)
recorder.addHandler(h)

def formatRecord(res, *args):
    xx = '(%s, \'%s\'),' % (str(args), str(res))
    return xx


class GitFacade(object):
    def __init__(self, git_dir):
        self.git_dir = git_dir

    def diffsByCommit(self, commitId):
        diffs = self._git_exec(['diff','--name-status', '-M', '-z', '%s^..%s' % (commitId, commitId)])
        recorder.debug('%s', formatRecord(diffs, commitId))
        return diffs

    def resetHard(self, ref):
        self._git_exec(['reset', '--hard', ref])
        recorder.debug('%s', formatRecord(None, ref))

    def resetBranches(self, branches):
        for branch in branches.keys():
            self.checkout(branch)
            self.resetHard(branches[branch])

    def checkout(self, ref):
        self._git_exec(['checkout', ref])
        recorder.debug('%s', formatRecord(None, ref))

    def addFile(self, file):
        # ivar: why errors=False?
        self._git_exec(['add', '-f', file], errors=False)
        recorder.debug('%s', formatRecord(None, file))

    def removeFile(self, file):
        self._git_exec(['rm', file])
        recorder.debug('%s', formatRecord(None, file))

    def pullRebase(self):
        self._git_exec(['pull', '--rebase'])
        recorder.debug('%s', formatRecord(None))

    def push(self):
        self._git_exec(['push'])
        recorder.debug('%s', formatRecord(None))

    def commit(self, msg, env=None):
        self._git_exec(['commit', '-m', msg], env=env)
        recorder.debug('%s', formatRecord(None, msg, env))

    def setTag(self, tagname, ref=''):
        tag = ['tag', '-f', tagname]
        if ref != '': tag.append(ref)
        self._git_exec(tag)
        recorder.debug('%s', formatRecord(None, tagname, ref))

    def removeTag(self, tagname):
        self._git_exec(['tag', '-d', tagname])
        recorder.debug('%s', formatRecord(None, tagname))

    def filesList(self):
        res = self._git_exec(['ls-files']).strip().split('\n')
        recorder.debug('%s', formatRecord(res))
        return res

    def branchHead(self, branch='HEAD'):
        res = self._git_exec(['show', '-s', '--format=%H', branch]).strip()
        recorder.debug('%s', formatRecord(res, branch))
        return res

    def commitMessage(self, commitId):
        res = self._git_exec(['log', '--format=%B', '%s^..%s' % (commitId, commitId)]).strip()
        recorder.debug('%s', formatRecord(res, commitId))
        return res


    def authorDate(self, commitId):
        res = datetime.strptime(self.authorDateStr(commitId), '%Y-%m-%d %H:%M:%S')
        return res
        
    def authorDateStr(self, commitId):
        res = self._git_exec(['show', '-s', '--format=%ai', commitId])[:19]
        recorder.debug('%s', formatRecord(res, commitId))
        return res

    def authorName(self, commitId):
        res = self._git_exec(['show', '-s', '--format=%an', commitId]).strip()
        recorder.debug('%s', formatRecord(res, commitId))
        return res

    def authorEmail(self, commitId):
        res = self._git_exec(['show', '-s', '--format=%ae', commitId]).strip()
        recorder.debug('%s', formatRecord(res, commitId))
        return res

    def blob(self, commitId, file):
        sha = self._git_exec(['ls-tree', commitId, file]).split(' ')[2].split('\t')[0]
        blob = self._git_exec(['cat-file', 'blob', sha])
        recorder.debug('%s', formatRecord(blob, commitId, file))
        return blob

    def mergeCommitFf(self, commitId, msg):
        self._git_exec(['merge', '--ff', '--commit', '-m', msg, commitId])
        recorder.debug('%s', formatRecord(None, commitId, msg))

    def mergeCommitNoFf(self, commitId, msg):
        self._git_exec(['merge', '--no-ff', '--commit', '-m', msg, commitId])
        recorder.debug('%s', formatRecord(None, commitId, msg))

    def mergeAbort(self):
        self._git_exec(['merge', '--abort'])
        recorder.debug('%s', formatRecord(None))

    def commitHistoryPathBlob(self, fromRef, toRef):
        # ivar: explore the need for x01 delimiters when using the -z flag
        res = self._git_exec(['log', '-z', '--first-parent', '--reverse', '--format=%x01%H%x02%s%x02%b', '%s..%s' % (fromRef, toRef)]).strip('\x01')
        recorder.debug('%s', formatRecord(res, fromRef, toRef))
        return res

    def reverseCommitHistoryList(self, fromRef, toRef='HEAD'):
        '''
        Return a reversed list of commit ids in the given range, i.e. in the order they were created.
        '''
        # ivar: why not use -z flag here?   
        commits = self._git_exec(['log', '--first-parent', '--reverse', '--format=%H', '%s..%s' % (fromRef, toRef)]).strip()
        res = commits.split('\n') if commits != '' else None
        logger.debug(res)
        recorder.debug('%s', formatRecord(res, fromRef, toRef))
        return res


    def _git_exec(self, cmd, **args):
        return util.popen('git', cmd, self.git_dir, **args)

