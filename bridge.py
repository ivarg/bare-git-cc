import os, stat
import re
import tempfile
from os.path import join, exists, dirname
from datetime import datetime, timedelta
import logging
import traceback

import users
from git import GitFacade
from clearcase import ClearcaseFacade
import util


logger = logging.getLogger('log.bgcc.file')


## Branch names
CC_BRANCH = 'master_cc'
MASTER = 'master'
# The CI_TAG tag is set at the commit most recently successfully checked in to clearcase,
# and is removed when no pending commit needs to be checked in.
# Thus, one should never see the tag unless something has gone wrong.
CI_TAG = 'master_ci'

# GIT_DIR = util.cfg.gitRoot() # 'c:/Development/gitcc-bridges/prime/br_main_electronic_trading_test/fmarket'
# CC_DIR =  util.cfg.ccRoot() # 'c:/Development/gitcc-bridges/prime/br_main_electronic_trading_test/view/base/TM_FObject/Financial/FMarket'
# CENTRAL = util.cfg.remote()


COMMIT_CACHE = 'commit_cache'

git_excludes = []

cc = git = None



def isPendingClearcaseChanges():
    '''
    Returns a bool telling whether there are unsynchronized changes in clearcase.
    '''
    date = git.commitDate(CC_BRANCH) + timedelta(seconds=1)
    since = datetime.strftime(date, '%d-%b-%Y.%H:%M:%S')
    history = cc.checkinHistoryReversed(since)
    logger.info('Pending file changes in Clearcase: %d', len(history))
    return len(history) > 0


class GitCCBridge(object):
    '''
    The bridge operates by having a dedicated branch (CC_BRANCH) reflecting the state of
    the clearcase view. Each new commit on CC_BRANCH is immediately merged on master and
    pushed to the remote, presumably shared, repository.
    New commits originating from the remote is pulled to master and then stored. When the
    time comes to synchronize with clearcase (checkin), e.g. when build and auto tests
    have verified integrity, each stored commit is subsequently merged on the CC_BRANCH and
    it's changes are checked in to clearcase.
    '''

    def __init__(self, cfg):
        global cc, git
        self.git_dir = cfg.gitRoot()
        self.cc_dir = cfg.ccRoot()
        self.remote = cfg.remote()
        git = GitFacade(self.git_dir)
        cc = ClearcaseFacade(self.cc_dir, cfg.getInclude(), cfg.getBranches())
        self.commit_cache = join(self.git_dir, '.git', COMMIT_CACHE)
        self.git_commits = []
        self.checkouts = []


    def newBridge(self, since=None):
        print str(datetime.now())[:19]
        if git.exists():
            raise Exception('Git repository already exists')
        if since:
            self._setandupdatecs(since)
            self._addccfilestogitrepo(since)
            self.cs = 'include \\\\appsto03\\config_specs\\prime\\main-windows.cspec' 
            self._restorecs()
            pass
        self.onNewClearcaseChanges()
        print str(datetime.now())[:19]

        
    def _restorecs(self):
        tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False)
        tmpfile.write(self.cs)
        tmpfile.close()
        # Set config spec and update (takes minutes)
        logger.info('[%s] Restoring the config spec and updating view. This may take several minutes...' % str(datetime.now())[:19])
        cc.setcs(tmpfile.name)
        logger.info('[%s] Done setting the config spec.' % str(datetime.now())[:19])
        os.remove(tmpfile.name)

    def _addccfilestogitrepo(self, since):
        # Initialize new git repo
        git.init()
        # For each file in the view, copy it to the git repo directory and add it to git
        filedict = cc.fileVersionDictionary()
        for file in filedict:
            ccfile = '%s@@%s' % (file,filedict[file])
            gitfile = os.path.join(git.git_dir, file)
            if not os.path.exists(os.path.dirname(gitfile)):
                # logger.info('creating dirs:', os.path.dirname(gitfile))
                os.makedirs(os.path.dirname(gitfile))
            cc.copyVobFile(ccfile, gitfile)
            git.addFile(gitfile)
        # Commit to git
        time = datetime.strptime(since, '%d-%b-%Y')
        env = os.environ
        env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = time.strftime('%Y-%m-%d %H:%M:%S')
        env['GIT_AUTHOR_NAME'] = env['GIT_COMMITTER_NAME'] = 'Anonymous'
        env['GIT_AUTHOR_EMAIL'] = env['GIT_COMMITTER_EMAIL'] = 'anonymous@sungard.com'
        git.commit('Repository snapshot at %s' % time.strftime('%Y-%m-%d'), env)


    def _setandupdatecs(self, since):
        # Get config spec
        self.cs = cc.catcs()
        # Set timestamp and save to temp file
        newcs = 'time %s\n%s' % (since, self.cs)
        tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False)
        tmpfile.write(newcs)
        tmpfile.close()
        # Set config spec and update (takes minutes)
        logger.info('[%s] Setting the config spec and updating view. This may take several minutes...' % str(datetime.now())[:19])
        cc.setcs(tmpfile.name)
        logger.info('[%s] Done setting the config spec.' % str(datetime.now())[:19])
        os.remove(tmpfile.name)


    def onDoCheckinToClearcase(self):
        '''
        Pull any new commits from remote to master.
        For each pending commit to be checked in, merge it onto the cc branch and check in
        it's file changes.
        '''
        self._loadGitCommits()
        head = git.branchHead(MASTER)
        self._updateMasterFromCentral() # ivar: This may not be safe since new commits have not been verified by CI
        if len(self.git_commits) == 0:
            logger.info('No pending commits to check in to Clearcase')
            return
        try:
            logger.info('Checking in new commits to Clearcase...')
            cc_head = git.branchHead(CC_BRANCH)
            self._mergeCommitsOnBranch(CC_BRANCH, self.git_commits)
            self._checkinCCBranch(cc_head)
        except CheckoutReservedException:
            # ivar: Need some smarter way to set bridge state after checkin failure
            git.resetBranches({MASTER:head, CC_BRANCH:cc_head})
            raise
        except Exception:
            git.resetBranches({MASTER:head, CC_BRANCH:cc_head})
            raise
        if cc.needUpdate():
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
        # if cc.needUpdate():
            # cc.update()
        self._loadGitCommits()
        commits = []
        git.checkout(CC_BRANCH)
        cslist = self._getClearcaseChanges()
        cchead = git.branchHead(CC_BRANCH)
        if cslist:
            logger.info('Committing Clearcase changes to Git')
            commits = self._commitToCCBranch(cslist)
            # commits.extend(self._addDiscoveredChanges())
        else:
            logger.info('Nothing to commit')
        if self.remote:
            self._updateMasterFromCentral()
        self._saveGitCommits()
        if commits:
            head = git.branchHead(MASTER)
            try:
                self._mergeCommitsOnBranch(MASTER, commits)
            except MergeConflictException as mce:
                git.resetHard(head)
                git.resetHard(cchead)
                raise mce
            if self.remote:
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
            cs.add(ClearcaseModify(time, self.git_dir, addition, addition_dict[addition]))
        for deletion in deletion_list:
            cs.add(ClearcaseDelete(time, self.git_dir, deletion))
        logger.info('Loading changeset [%s]', cs.comment.split('\n')[0])
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
        logger.info('Found repository discrepancies - aligning Git with CC...')
        return self.alignGitToClearcase(addition_dict, deletion_list)


    def _updateMasterFromCentral(self):
        '''
        Get latest from remote (central) and save commits for later merging
        '''
        git.checkout(MASTER)
        head = git.branchHead()
        git.updateRemote()
        if head != git.branchHead(self.remote):
            git.pullRebase() # ivar: Conflict? Can this raise if we enter in a merge?
            commits = git.reverseCommitHistoryList(head)
##### Only during development!! #####
            # commits = list(set(commits)-set(self.git_commits))
#####################################
            if commits:
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
            try:
                git.mergeCommitFf(commitId, msg)
                logger.info('Merged on branch %s commit %s', branch, commitId[:7])
            except Exception as e:
                logger.error('Exception caught: %s', str(e))
                git.mergeAbort()
                raise MergeConflictException(commitId, branch, str(e))


    def _checkinCCBranch(self, old_head):
        '''
        Expects the cc branch to be up to date with new changes from the central git repository
        Given the cc branch head representing the latest changes in clearcase, try to checkin all commits (sequentially) added from the central git repository.
        For each commit, first checkout all necessary files reserved, then write changes and make modifications, and last, checkin all files.
        This is the expected behavior. The raw functionality is to simply try to checkin to clearcase all commits between the old_head and HEAD on the cc branch.
        '''
        git.checkout(CC_BRANCH)
        history = git.commitHistoryPathBlob(old_head, CC_BRANCH)
        logger.info('Preparing to check in...')
        for hentry in history.split('\x01'):
            commitId, subject, body = hentry.split('\x02')
            comment = subject if body == '\n' else '%s\n%s' % (subject, body)
            comment = comment.strip('\n')
            commitToCC = CommitToClearcase(commitId, comment, self.cc_dir)
            commitToCC.checkoutClearcaseFiles()
            commitToCC.updateClearcaseFiles()
            commitToCC.checkinClearcaseFiles()
            logger.info('Checked in to Clearcase commit %s', commitId)
            git.setTag(CI_TAG, commitId)
        git.removeTag(CI_TAG)


    def _saveGitCommits(self):
        if len(self.git_commits) == 0:
            return
        logger.info('Saving commits cache: %s', self.git_commits)
        concat_fn = lambda x,y: '%s\n%s' % (x,y)
        commit_blob = reduce(concat_fn, self.git_commits)
        ff = open(self.commit_cache, 'w')
        ff.write(commit_blob)
        ff.close()


    def _loadGitCommits(self):
        if exists(self.commit_cache):
            ff = open(self.commit_cache, 'r')
            blob = ff.read()
            ff.close()
            self.git_commits = blob.split('\n')
            os.remove(self.commit_cache)
            logger.info('Loading commits cache: %s', self.git_commits)


    def _getClearcaseChanges(self):
        '''
        Retreives latest changes from clearcase and commits them to the cc branch (CC_BRANCH)
        '''
        logger.debug('')
        date = git.commitDate(CC_BRANCH) + timedelta(seconds=1)
        since = datetime.strftime(date, '%d-%b-%Y.%H:%M:%S')
        history = cc.checkinHistoryReversed(since)
        if len(history) == 0:
            return None
        cslist = []

        _, t_time, t_user, _, _, t_comment = history[0].split('\x01')
        changeset = ClearcaseChangeSet(t_user, t_comment)
        for line in history:
            type, time, user, file, version, comment = line.split('\x01')

            if type == 'checkinversion':
                if user != t_user or comment != t_comment:
                    if not changeset.isempty():
                        logger.info('Loading changeset "%s" - [ %s ]', changeset.comment.split('\n')[0].strip(), changeset)
                        cslist.append(changeset)
                    changeset = ClearcaseChangeSet(user, comment)
                changeset.add(ClearcaseModify(time, self.git_dir, file, version))
                t_time, t_user, t_comment = time, user, comment

            elif type == 'checkindirectory version' and comment.startswith('Uncataloged file element'):
                if util.timeDiff(t_time, time) > 4:
                    if not changeset.isempty():
                        logger.info('Loading changeset "%s" - [ %s ]', changeset.comment.split('\n')[0].strip(), changeset)
                        cslist.append(changeset)
                    changeset = ClearcaseChangeSet(user, comment)
                changeset.add(createClearcaseDelete(time, self.git_dir, file, version, comment))
                t_time, t_user, t_comment = time, user, comment

        if not changeset.isempty():
            logger.info('Loading changeset "%s" - [ %s ]', changeset.comment.split('\n')[0].strip(), changeset)
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
    def __init__(self, commitId, comment, cc_dir):
        self.commitId = commitId
        self.comment = comment
        self.diffs = self._getCommitFileChanges(self.commitId, cc_dir)

    def checkoutClearcaseFiles(self):
        self._checkoutReservedOrRaise(self._filesToCheckout())

    def updateClearcaseFiles(self):
        try:
            for diff in self.diffs:
                diff.updateCCArea()
        except Exception as e:
            traceback.print_exc()
            for file in self._filesToCheckout():
                cc.undoCheckout(file)
            raise UpdateCCAreaException(diff.commitId, str(e))

    def checkinClearcaseFiles(self):
        files = []
        for diff in self.diffs:
            files.extend(diff.checkins)
        files = list(set(files)) # remove duplicates
        for file in files:
            cc.checkin(file, self.comment)
            logger.debug('Checked in to Clearcase file %s', file)

    def _filesToCheckout(self):
        files = []
        for diff in self.diffs:
            files.extend(diff.checkouts)
        return list(set(files)) # remove duplicates

    def _checkoutReservedOrRaise(self, files):
        passed = []
        notpassed = []
        for ff in files:
            try:
                cc.checkout(ff)
                passed.append(ff)
            except Exception as e:
                notpassed.append(ff)
                error = str(e)
        if len(notpassed) > 0:
            for pp in passed:
                cc.undoCheckout(pp)
            raise CheckoutReservedException(notpassed, error)
        return passed # Only for testability

    def _getCommitFileChanges(self, commitId, cc_dir):
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
            if symbol == 'R':
                diffs.append(RenameDiff(commitId, cc_dir, file, split.pop(0)))
            elif symbol == 'A':
                diffs.append(AddDiff(commitId, cc_dir, file))
            elif symbol == 'D':
                diffs.append(DelDiff(cc_dir, file))
            elif symbol == 'M':
                diffs.append(ModDiff(commitId, cc_dir, file))
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

    def __str__(self):
        return ','.join(map(lambda a: a.file, self.changes))

    def isempty(self):
        return len(self.changes) == 0

    def add(self, change):
        self.changes.append(change)
        self.time = datetime.strptime(change.time, '%Y%m%d.%H%M%S')

    def commitToGit(self):
        for change in self.changes:
            change.stage()
        # if cc.needUpdate():
            # cc.update()
        env = os.environ
        env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = self.time.strftime('%Y-%m-%d %H:%M:%S')
        env['GIT_AUTHOR_NAME'] = env['GIT_COMMITTER_NAME'] = users.getUserName(self.userId).encode('latin-1')
        env['GIT_AUTHOR_EMAIL'] = env['GIT_COMMITTER_EMAIL'] = str(users.getUserEmail(self.userId))
        if self.comment.strip() == '':
            self.comment = '<empty comment>'
        try:
            git.commit(self.comment, env)
            logger.info('Committed to branch %s change [%s] -> %s', CC_BRANCH, self.comment.split('\n')[0].strip(), git.branchHead()[:7])
            return git.branchHead()
        except Exception as e:
            if re.search('nothing( added)? to commit', e.args[0]) == None:
                raise
            logger.info('Nothing new to commit [%s]', self.comment.split('\n')[0].strip())
            return None


class ClearcaseModify(object):
    def __init__(self, time, git_dir, file, version):
        self.time = time
        self.git_dir = git_dir
        self.file = file
        self.version = version

    def stage(self):
        toFile = join(self.git_dir, self.file)
        util.prepareForCopy(toFile)
        ccfile = '%s@@%s' % (self.file, self.version)
        cc.copyVobFile(ccfile, toFile)
        git.addFile(self.file)


def createClearcaseDelete(time, git_dir, dir, version, comment):
    # dir = join(git_dir, dir)
    file = re.search('\"(.+)\"', comment).group(1)
    file = join(dir, file)
    return ClearcaseDelete(time, git_dir, file)


class ClearcaseDelete(object):
    def __init__(self, time, git_dir, file):
        self.time = time
        self.git_dir = git_dir
        self.file = file

    # ivar: if needed, give git_dir as an argument to stage()
    def stage(self):
        if not exists(join(self.git_dir, self.file)):
            logger.info('File marked for deletion does not exist in the git repository: %s' % join(self.git_dir, self.file))
            return
        git.removeFile(self.file)




class ModDiff():
    def __init__(self, commitId, viewroot, file):
        self.commitId = commitId
        self.viewroot = viewroot
        self.file = file
        self.checkouts = self.checkins = [self.file]

    def updateCCArea(self):
        blob = git.blob(self.commitId, self.file)
        f = open(join(self.viewroot, self.file), 'wb')
        f.write(blob)
        f.close()


class AddDiff():
    def __init__(self, commitId, viewroot, file):
        self.commitId = commitId
        self.viewroot = viewroot
        self.file = file
        self._extractCCFiles()

    def _extractCCFiles(self):
        dst = dirname(self.file)
        path = []
        while not exists(join(self.viewroot, dst)):
            path.append(dst)
            dst = dirname(dst)
        dst = '.' if dst == '' else dst
        self.checkouts = [dst]
        self.checkins = [self.file, dst]
        self.checkins.extend(path)

    def updateCCArea(self):
        dir = dirname(self.file)
        path = []
        while not exists(join(self.viewroot, dir)):
            path.append(dir)
            dir = dirname(dir)
        while len(path) > 0:
            cc.addDirectory(path.pop())
        blob = git.blob(self.commitId, self.file)
        f = open(join(self.viewroot, self.file), 'wb')
        f.write(blob)
        f.close()
        cc.addFile(self.file)


class DelDiff():
    def __init__(self, viewroot, file):
        self.viewroot = viewroot
        self.file = file
        self._extractCCFiles()

    def _extractCCFiles(self):
        '''
        Collect which elements to checkout and checkin on, respectively.
        '''
        dst = dirname(self.file)
        while not exists(join(self.viewroot, dst)):
            dst = dirname(dst)
        dst = '.' if dst == '' else dst
        self.checkouts = [dst]
        self.checkins = [dst]

    def updateCCArea(self):
        ## We are not purging empty directory elements after delete
        cc.removeFile(self.file)


class RenameDiff():
    def __init__(self, commitId, viewroot, file, dst):
        self.commitId = commitId
        self.viewroot = viewroot
        self.file = file
        self.dst = dst
        self._extractCCFiles()

    def _extractCCFiles(self):
        src_dir = dirname(self.file)
        src_dir = '.' if src_dir == '' else src_dir
        dst_dir = dirname(self.dst)
        path = []
        while not exists(join(self.viewroot, dst_dir)):
            path.append(dst_dir)
            dst_dir = dirname(dst_dir)
        dst_dir = '.' if dst_dir == '' else dst_dir
        self.checkouts = [self.file, src_dir, dst_dir]
        self.checkins = [self.dst, src_dir, dst_dir]
        self.checkins.extend(path)

    def updateCCArea(self):
        # Copy the contents of the 'new' file in the git area to the 'old' file in the cc area
        blob = git.blob(self.commitId, self.dst)
        f = open(join(self.viewroot, self.file), 'wb')
        f.write(blob)
        f.close()

        dst_dir = dirname(self.dst)
        path = []
        while not exists(join(self.viewroot, dst_dir)):
            path.append(dst_dir)
            dst_dir = dirname(dst_dir)
        while len(path) > 0:
            cc.addDirectory(path.pop())
        cc.moveFile(self.file, self.dst)

