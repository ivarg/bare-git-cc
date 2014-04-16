import os, stat, os.path
import tempfile
import re
import util
import logging

# This is temporary stuff just for recording, set level to DEBUG to enable
logger = logging.getLogger('log.bgcc.file')


def formatRecord(res, *args):
    xx = '(%s, \'%s\'),' % (str(args), str(res))
    return xx


class ClearcaseFacade(object):
    def __init__(self, cc_dir, includes, branch, recursive=True):
        self.cc_dir = cc_dir
        if includes != ['']:
            self.includes = includes
        else:
            self.includes = None
        self.branch = branch
        self.recursive = recursive

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
        return len(hits) > 0

    def fileVersionDictionary(self):
        '''
        Return a dictionary containing all versioned files in the clearcase view, with their corresponding branch/version.
        '''
        ls = ['ls', '-long', '-vob']
        if self.recursive:
            ls.append('-recurse')
        if self.includes:
            ls.extend(self.includes)
        vob = self._cc_exec(ls)
        vob = re.findall('^(version.*)', vob, re.M)
        fileversions = map(lambda ss: re.match('version\s+(.*?@@[^\s]+)', ss).group(1).replace('\\','/'), vob)
        vobdict = {}
        for fv in fileversions:
            if fv.startswith('./'):
                fv = fv[2:]
            obj = re.match('(.+)@@(.+)', fv, re.M)
            if not obj:
                logger.error('No cc version format: %s', fv)
            else:
                vobdict[obj.group(1)] = obj.group(2)
        return vobdict

    def checkinHistoryReversed(self, since):
        lsh = ['lsh', '-fmt', '%o%m\001%Nd\001%u\001%En\001%Vn\001%Nc\n']
        if self.recursive:
            lsh.append('-recurse')
        lsh.extend(['-since', since])
        if self.includes:
            lsh.extend(self.includes) ## To filter our folders specified in configuration
        blob = self._cc_exec(lsh).replace('\\', '/') # clean up windows separator ugliness
        ptrn = '^(checkin.+?\x01.+?\x01.+?\x01.+?\x01.+%s/\d+\x01.*)' % self.branch
        filtered = re.findall(ptrn, blob, re.M)
        filtered.reverse()
        # logger.debug(blob)
        logger.debug(self.branch)
        logger.debug(ptrn)
        logger.debug(filtered)
        return filtered

    def copyVobFile(self, ccfile, dest):
        if os.path.exists(dest):
            os.remove(dest)
        self._cc_exec(['get','-to', dest, ccfile])
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IWRITE)

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

    def catcs(self):
        out = self._cc_exec(['catcs'])
        # return re.match('include\s(.*)', out).group(1)
        return out

    def setcs(self, csfile):
        print 'setting config spec to: %s' % csfile
        self._cc_exec(['setcs', csfile])
        print 'done'


    def _cc_exec(self, cmd, **args):
        logger.debug('cleartool %s' % ' '.join(cmd))
        return util.popen('cleartool', cmd, self.cc_dir, **args)





