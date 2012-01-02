

class ModDiff():
    def __init__(self, commitId, file):
        self.commitId = commitId
        self.file = file
        self.checkouts = self.checkins = [self.file]

    def updateCCArea(self):
        blob = git_exec(['cat-file', 'blob', getBlob(self.commitId, self.file)])
        write(join(CC_DIR, self.file    ), blob)


class AddDiff():
    def __init__(self, commitId, file):
        self.commitId = commitId
        self.file = file
        self._extractCCFiles()

    def _extractCCFiles(self):
        dst = dirname(self.file)
        path = []
        while not exists(join(CC_DIR, dst)):
            path.append(dst)
            dst = dirname(dst)
        dst = '.' if dst == '' else dst
        self.checkouts = [dst]
        self.checkins = [self.file, dst]
        self.checkins.extend(path)

    def updateCCArea(self):
        dir = dirname(self.file)
        path = []
        while not exists(join(CC_DIR, dir)):
            path.append(dir)
            dir = dirname(dir)
        while len(path) > 0:
            cc_exec(['mkelem', '-nc', '-eltype', 'directory', path.pop()])
        blob = git_exec(['cat-file', 'blob', getBlob(self.commitId, self.file)])
        write(join(CC_DIR, self.file), blob)
        cc_exec(['mkelem', '-nc', self.file])


class DelDiff():
    def __init__(self, file):
        self.file = file
        self._extractCCFiles()

    def _extractCCFiles(self):
        '''
        Collect which elements to checkout and checkin on, respectively.
        '''
        dst = dirname(self.file)
        while not exists(join(CC_DIR, dst)):
            dst = dirname(dst)
        dst = '.' if dst == '' else dst
        self.checkouts = [dst]
        self.checkins = [dst]

    def updateCCArea(self):
        ## We are not purging empty directory elements after delete
        cc_exec(['rm', self.file])


class RenameDiff():
    def __init__(self, commitId, src, dst):
        self.commitId = commitId
        self.src = src
        self.dst = dst
        self._extractCCFiles()

    def _extractCCFiles(self):
        src_dir = dirname(self.src)
        src_dir = '.' if src_dir == '' else src_dir
        dst_dir = dirname(self.dst)
        path = []
        while not exists(join(CC_DIR, dst_dir)):
            path.append(dst_dir)
            dst_dir = dirname(dst_dir)
        dst_dir = '.' if dst_dir == '' else dst_dir
        self.checkouts = [self.src, src_dir, dst_dir]
        self.checkins = [self.dst, src_dir, dst_dir]
        self.checkins.extend(path)

    def updateCCArea(self):
        dst_dir = dirname(self.dst)
        path = []
        while not exists(join(CC_DIR, dst_dir)):
            path.append(dst_dir)
            dst_dir = dirname(dst_dir)
        while len(path) > 0:
            cc_exec(['mkelem', '-nc', '-eltype', 'directory', path.pop()])
        cc_exec(['mv', '-nc', self.src, self.dst])
