import os, stat
import re
import tempfile
from os.path import join, exists
from datetime import datetime, timedelta
import logging

import users
import git
import clearcase
import util
from diff import AddDiff, DelDiff, ModDiff, RenameDiff

logger = logging.getLogger()

"""
Things to test/verify:
- Additions and renames in Git propagate to Clearcase
- Additions and deletes in Clearcase propagates to Git
- How can we check sync status?
- How can we identify clearcase renames?
- git exclude - how to prevent files in git to get added in cc?
"""

## Branch names
CC_BRANCH = 'master_cc'
MASTER = 'master'
CENTRAL = 'remotes/central/master'
CI_TAG = 'master_ci'

DELIM = '|'
GIT_DIR = 'c:/Development/gitcc-bridges/prime/br_main_electronic_trading_test/fmarket'
CC_DIR = 'c:/Development/gitcc-bridges/prime/br_main_electronic_trading_test/view/base/TM_FObject/Financial/FMarket'
LOG_FILE = 'c:/Development/gitcc-bridges/prime/br_main_electronic_trading_test/fmarket/.debug.log'
COMMIT_CACHE = 'commit_cache'
COMMIT_CACHE_FILE = join(GIT_DIR, '.git', COMMIT_CACHE)

git_excludes = []

cfg = util.GitConfigParser(GIT_DIR, MASTER)
cfg.read()

git = git.GitFacade(GIT_DIR)
cc = clearcase.ClearcaseFacade(CC_DIR)


def isPendingClearcaseChanges():
    date = git.authorDate(CC_BRANCH) + timedelta(seconds=1)
    since = datetime.strftime(date, '%d-%b-%Y.%H:%M:%S')
    history = cc.checkinHistoryReversed(since, cfg.getInclude())
    logger.info('Pending file changes in Clearcase: %d', len(history))
    return len(history) > 0


class GitCCBridge(object):
    def __init__(self):
        self.git_commits = []
        self.checkouts = []
        self._loadGitCommits()

    def onDoCheckinToClearcase(self):
        '''
        Stuff is verified on central and we should do a checkin to clearcase.
        This can be executed only if we can to reserved checkouts on all concerned files.
        If not, we must throw an exception.
        First, we get the latest from Central.
        If all files are then successfully checked out, we merge the saved commits (git_commits)
        on the CC branch, one at a time, and for each merge, we checkin the files to clearcase,
        keeping the files checked out.
        Finally, we undo our reserved checkouts.
        '''
        self._updateMasterFromCentral()
        if len(self.git_commits) == 0:
            logger.info('No pending commits to check in to Clearcase')
            return
        try:
            logger.info('Checking in new commits to Clearcase...')
            cc_head = git.branchHead(CC_BRANCH)
            git.setTag(CI_TAG)
            self._mergeCommitsOnBranch(CC_BRANCH, self.git_commits)
            self._checkinCCBranch(cc_head)
        except MergeConflictException as mce:
            git.resetHard(cc_head)
            raise mce
        except CheckoutReservedException as cre:
            git.resetHard(cc_head)
            raise cre
        if not cc.isUpdated():
            logger.warning('Clearcase needs updating!')
            cc.update()
            logger.info('Clearcase updated')
        git.resetHard(MASTER)


    def onNewClearcaseChanges(self):
        '''
        + Make git commits from clearcase changes and add them to CC_BRANCH
        + Rebase master from CENTRAL
        + Merge clearcase commits on master (risk of conflict here)
        + Push to central
        '''
        logger.info('Committing Clearcase changes to Git')
        commits = []
        cslist = self._getClearcaseChanges()
        if cslist:
            commits = self._commitToCCBranch(cslist)
        commits.extend(self._addDiscoveredChanges())
        self._updateMasterFromCentral()
        self._saveGitCommits()
        if commits:
            head = git.branchHead(MASTER)
            try:
                self._mergeCommitsOnBranch(MASTER, commits)
            except MergeConflictException as mce:
                git.resetHard(head)
                raise mce
            self._pushMasterToCentral()


    def syncReport(self):
        cc_snapshot = cc.fileVersionDictionary()
        cc_files = cc_snapshot.keys()
        git.checkout(CC_BRANCH)
        git_files = git.filesList()

        # Filter out git files not synced in clearcase
        git_files = list(set(git_files) - set(git_excludes))

        added_in_cc = list(set(cc_files) - set(git_files))
        added_in_git = list(set(git_files) - set(cc_files))

        cc_dict = dict()
        map(lambda xx: cc_dict.update({xx : cc_snapshot.get(xx)}), added_in_cc)
        return (cc_dict, added_in_git)



    def alignGitToClearcase(self, addition_dict, deletion_list):
        cs = ClearcaseChangeSet('Unknown', 'Anonymous file changes in Clearcase')
        time = datetime.now().strftime('%Y%m%d.%H%M%S')
        for addition in addition_dict.keys():
            cs.add(ClearcaseModify(time, addition, addition_dict[addition]))
        for deletion in deletion_list:
            cs.add(ClearcaseDelete(time, deletion))
        return self._commitToCCBranch([cs])


    def _addDiscoveredChanges(self):
        '''
        Check for discrepancies between git and clearcase. If any are found, update 
        git to be aligned with clearcase, and return the resulting commitId.
        The purpose is primarily to discover renames in clearcase, but is also a way 
        to ensure synchronization between git and clearcase.
        '''
        (addition_dict, deletion_list) = self.syncReport()
        if len(addition_dict) == len(deletion_list) == 0:
            return []
        return self.alignGitToClearcase(addition_dict, deletion_list)


    def _updateMasterFromCentral(self):
        '''
        Get latest from remote (central) and save commits for later merging
        '''
        git.checkout(MASTER)
        head = git.branchHead()
        if head != git.branchHead(CENTRAL):
            git.pullRebase() # ivar: Conflict? Can this raise if we enter in a merge?
            commits = git.reverseCommitHistoryList(head)
##### Only during development!! #####
            commits = list(set(commits)-set(self.git_commits))
#####################################
            self.git_commits.extend(commits)


    def _mergeCommitsOnBranch(self, branch, commits):
        '''
        Checks out the branch and sequentially merges the commits onto it.
        In case of a conflict, the merge is aborted and an exception is raised.
        ivar: When the conflict is resolved, the resulting merge commit needs to
        be checked in to clearcase.
        '''
        git.checkout(branch)
        for commitId in commits:
            msg = git.commitMessage(commitId)
            env = os.environ
            env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = git.authorDateStr(commitId)
            env['GIT_AUTHOR_NAME'] = env['GIT_COMMITTER_NAME'] = git.authorName(commitId)
            env['GIT_AUTHOR_EMAIL'] = env['GIT_COMMITTER_EMAIL'] = git.authorEmail(commitId)
            try:
                git.mergeCommitFf(commitId, msg)
                logger.debug('Merged on branch %s commit %s', branch, commitId)
            except Exception as e:
                git.mergeAbort()
                raise MergeConflictException(commitId, branch, getattr(e, 'message'))


    def _checkinCCBranch(self, old_head):
        '''
        Expects the cc branch to be up to date with new changes from the central git repository
        Given the cc branch head representing the latest changes in clearcase, try to checkin all commits (sequentially) added from the central git repository.
        For each commit, first checkout all necessary files reserved, then write changes and make modifications, and last, checkin all files.
        This is the expected behavior. The raw functionality is to simply try to checkin to clearcase all commits between the old_head and HEAD on the cc branch.
        '''
        git.checkout(CC_BRANCH)
        history = git.commitHistoryPathBlob(old_head, CC_BRANCH)
        for hentry in history.split('\x01'):
            commitId, subject, body = hentry.split('\x02')
            comment = subject if body == '\n' else '%s\n%s' % (subject, body)
            comment = comment.strip('\n')
            commitToCC = CommitToClearcase(commitId, comment)
            commitToCC.checkoutClearcaseFiles()
            commitToCC.updateClearcaseFiles()
            commitToCC.checkinClearcaseFiles()
            logger.debug('Checked in to Clearcase commit %s', commitId)
            git.setTag(CI_TAG, commitId)
        git.removeTag(CI_TAG)


    def _saveGitCommits(self):
        if len(self.git_commits) == 0:
            return
        concat_fn = lambda x,y: '%s\n%s' % (x,y)
        commit_blob = reduce(concat_fn, self.git_commits)
        ff = open(COMMIT_CACHE_FILE, 'w')
        ff.write(commit_blob)
        ff.close()


    def _loadGitCommits(self):
        if exists(COMMIT_CACHE_FILE):
            ff = open(COMMIT_CACHE_FILE, 'r')
            blob = ff.read()
            ff.close()
            self.git_commits = blob.split('\n')
            os.remove(COMMIT_CACHE_FILE)
            logger.info('Loading commits cache: %s', self.git_commits)
            

    def _getClearcaseChanges(self):
        '''
        Retreives latest changes from clearcase and commits them to the cc branch (CC_BRANCH)
        '''
        date = git.authorDate(CC_BRANCH) + timedelta(seconds=1)
        since = datetime.strftime(date, '%d-%b-%Y.%H:%M:%S')
        history = cc.checkinHistoryReversed(since, cfg.getInclude())
        if len(history) == 0:
            return None
        cslist = []
        type, _, user, _, _, comment = history[0].split('\x01')
        changeset = ClearcaseChangeSet(user, comment)
        for line in history:
            type, time, user, file, version, comment = line.split('\x01')
            if user != changeset.userId or comment != changeset.comment:
                if not changeset.isempty():
                    cslist.append(changeset)
                changeset = ClearcaseChangeSet(user, comment)
            if type == 'checkinversion':
                changeset.add(ClearcaseModify(time, file, version))
            elif type == 'checkindirectory version':
                if comment.startswith('Uncataloged file element'):
                    changeset.add(createClearcaseDelete(time, file, version, comment))
        if not changeset.isempty():
            cslist.append(changeset)
        return cslist


    def _commitToCCBranch(self, cslist):
        commits = []
        git.checkout(CC_BRANCH)
        for changeset in cslist:
            commitId = changeset.commitToGit()
            if commitId:
                commits.append(commitId)
        return commits


    def _pushMasterToCentral(self):
        '''
        Push CC stuff from master to remote central
        '''
        git.checkout(MASTER)
        git.push()




class CheckoutReservedException(Exception):
    pass

class UpdateCCAreaException(Exception):
    pass

class MergeConflictException(Exception):
    pass


class CommitToClearcase(object):
    '''
    This is a helper class to perform updates in Clearcase corresponding to
    commits in Git.
    '''
    def __init__(self, commitId, comment):
        self.commitId = commitId
        self.comment = comment
        self.diffs = self._getCommitFileChanges(self.commitId)

    def checkoutClearcaseFiles(self):
        files = []
        for diff in self.diffs:
            files.extend(diff.checkouts)
        # ivar: duplicates shouldn't be present since all diffs come from one single commit
        files = list(set(files)) # remove duplicates
        self._checkoutReservedOrRaise(files)

    def updateClearcaseFiles(self):
        try:
            for diff in self.diffs:
                diff.updateCCArea()
        except Exception as e:
            for file in diff.checkouts:
                cc.undoCheckout(file)
            raise UpdateCCAreaException(diff.file, getattr(e, 'message'))

    def checkinClearcaseFiles(self):
        files = []
        for diff in self.diffs:
            files.extend(diff.checkins)
        files = list(set(files)) # remove duplicates
        for file in files:
            cc.checkin(file, self.comment)
            logger.debug('Checked in to Clearcase file %s', file)

    def _checkoutReservedOrRaise(self, files):
        passed = []
        notpassed = []
        for ff in files:
            try:
                cc.checkout(ff)
                passed.append(ff)
            except Exception as e:
                notpassed.append(ff)
                error = getattr(e, 'message')
        if len(notpassed) > 0:
            for pp in passed:
                cc.undoCheckout(pp)
            raise CheckoutReservedException(notpassed, error)
        return passed # Only for testability

    def _getCommitFileChanges(self, commitId):
        '''
        Given a commit, return a list with Diff objects, containing type symbol and files affected.
        '''
        diffs = []
        status = git.diffsByCommit(commitId)
        status = status.strip(' \x00')
        split = status.split('\x00')
        while len(split) > 1:
            symbol = split.pop(0)[0] # first char
            file = split.pop(0)
            if file == CACHE_FILE:
                continue
            if symbol == 'R':
                diffs.append(RenameDiff(commitId, file, split.pop(0)))
            elif symbol == 'A':
                diffs.append(AddDiff(commitId, file))
            elif symbol == 'D':
                diffs.append(DelDiff(file))
            elif symbol == 'M':
                diffs.append(ModDiff(commitId, file))
            else:
                raise Exception("Unknown status on file: (%s,%s)" % (symbol, file))
        return diffs




class ClearcaseChangeSet(object):
    '''
    This is a helper class to perform updates in Git corresponding to a coherent set
    of changes in Clearcase.
    '''
    def __init__(self, userId, comment):
        self.userId = userId
        self.comment = comment
        self.changes = []
        self.time = None

    def isempty(self):
        return len(self.changes) == 0

    def add(self, change):
        self.changes.append(change)
        self.time = datetime.strptime(change.time, '%Y%m%d.%H%M%S')

    def commitToGit(self):
        for change in self.changes:
            change.stage()
        # cache.write()
        env = os.environ
        env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = self.time.strftime('%Y-%m-%d %H:%M:%S')
        env['GIT_AUTHOR_NAME'] = env['GIT_COMMITTER_NAME'] = users.getUserName(self.userId).encode()
        env['GIT_AUTHOR_EMAIL'] = env['GIT_COMMITTER_EMAIL'] = str(users.getUserEmail(self.userId))
        try:
            git.commit(self.comment, env)
            return git.branchHead()
        except Exception as e:
            if re.search('nothing( added)? to commit', e.args[0]) == None:
                raise
            logger.info('Nothing new to commit')
            return None


class ClearcaseModify(object):
    def __init__(self, time, file, version):
        self.time = time
        self.file = file
        self.version = version

    def stage(self):
        toFile = join(GIT_DIR, self.file)
        util.prepareForCopy(toFile)
        ccfile = '%s@@%s' % (self.file, self.version)
        cc.copyVobFile(ccfile, toFile)
        git.addFile(self.file)


def createClearcaseDelete(time, dir, version, comment):
    dir = join(GIT_DIR, dir)
    file = re.search('\"(.+)\"', comment).group(1)
    file = join(dir, file)
    return ClearcaseDelete(time, file)


class ClearcaseDelete(object):
    def __init__(self, time, file):
        self.time = time
        self.file = file

    def stage(self):
        if not exists(self.file):
            logger.info('File marked for deletion does not exist in the git repository: %s' % self.file)
            return
        git.removeFile(self.file)



