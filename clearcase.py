import os, stat
import tempfile
import re
import util
import logging

# This is temporary stuff just for recording, set level to DEBUG to enable
logger = logging.getLogger('log.bgcc.file')
recorder = logging.getLogger('log.bgcc.clearcase')
# h = logging.FileHandler('ccrecorder.log', 'w')
# h.setFormatter(logging.Formatter('%(message)s'))
# h.setLevel(logging.INFO)
# recorder.addHandler(h)


def formatRecord(res, *args):
    xx = '(%s, \'%s\'),' % (str(args), str(res))
    return xx


class ClearcaseFacade(object):
    def __init__(self, cc_dir, includes, branches):
        self.cc_dir = cc_dir
        self.includes = includes
        self.branches = branches

    def needUpdate(self):
        '''
        Checks whether an update would result in any changes to the clearcase
        working files.
        '''
        (fd, tmpfile) = tempfile.mkstemp()
        os.close(fd)
        self._cc_exec(['update', '-print', '-ove', '-log', tmpfile])
        ff = open(tmpfile, 'r')
        buf = ff.read()
        ff.close()
        os.remove(tmpfile)
        hits = re.findall('^Updated:', buf, re.M)
        recorder.debug('%s', formatRecord(len(hits) > 0))
        return len(hits) > 0

    def fileVersionDictionary(self):
        '''
        Return a dictionary containing all versioned files in the clearcase view, with their corresponding branch/version.
        '''
        ls = ['ls', '-long', '-recurse', '-vob']
        ls.extend(self.includes)
        vob = self._cc_exec(ls)
        vob = re.findall('^(version.*)', vob, re.M)
        fileversions = map(lambda ss: re.match('version\s+([^\s]+)', ss).group(1).replace('\\','/'), vob)
        vobdict = {}
        for fv in fileversions:
            obj = re.match('[\./]*(.+)@@(.+)', fv, re.M)
            if not obj:
                logger.error('No cc version format: %s', fv)
            else:
                vobdict[obj.group(1)] = obj.group(2)
        recorder.debug('%s', formatRecord(vobdict))
        return vobdict

    def checkinHistoryReversed(self, since):
        lsh = ['lsh', '-fmt', '%o%m\001%Nd\001%u\001%En\001%Vn\001%Nc\n', '-recurse', '-since', since]
        lsh.extend(self.includes) ## To filter our folders specified in configuration
        blob = self._cc_exec(lsh).replace('\\', '/') # clean up windows separator ugliness
        ptrn = '^(checkin.+?\x01.+?\x01.+?\x01.+?\x01.+[%s]/\d+\x01.*)' % ','.join(self.branches)
        filtered = re.findall(ptrn, blob, re.M)
        filtered.reverse()
        logger.debug(filtered)
        recorder.debug('%s', formatRecord(filtered, since, self.includes))
        return filtered

    def copyVobFile(self, ccfile, dest):
        self._cc_exec(['get','-to', dest, ccfile])
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IWRITE)
        recorder.debug('%s', formatRecord(None, ccfile, dest))

    def undoCheckout(self, file):
        self._cc_exec(['unco', '-rm', file])

    def update(self):
        self._cc_exec(['update', '-overwrite'])

    def checkin(self, file, comment):
        self._cc_exec(['ci', '-identical', '-c', comment, file])

    def checkout(self, file):
        self._cc_exec(['co', '-reserved', '-nc', file])

    def addDirectory(self, dir):
        self._cc_exec(['mkelem', '-nc', '-eltype', 'directory', dir])

    def addFile(self, file):
        self._cc_exec(['mkelem', '-nc', file])

    def removeFile(self, file):
        self._cc_exec(['rm', file])

    def moveFile(self, src, dst):
        self._cc_exec(['mv', '-nc', src, dst])


    def _cc_exec(self, cmd, **args):
        return util.popen('cleartool', cmd, self.cc_dir, **args)





