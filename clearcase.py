import os, stat
import tempfile
import re
from util import popen, Loggable

class ClearcaseFacade(Loggable):
    def __init__(self, cc_dir):
        self.cc_dir = cc_dir

    def isUpdated(self):
        '''
        Checks whether an update would result in any changes to the clearcase
        working files.
        '''
        self.printSignature()
        (fd, tmpfile) = tempfile.mkstemp()
        os.close(fd)
        self._cc_exec(['update', '-print', '-ove', '-log', tmpfile])
        ff = open(tmpfile, 'r')
        buf = ff.read()
        ff.close()
        os.remove(tmpfile)
        hits = re.findall('^Updated:', buf, re.M)
        return len(hits) == 0

    def fileVersionDictionary(self):
        '''
        Return a dictionary containing all versioned files in the clearcase view, with their corresponding branch/version.
        '''
        self.printSignature()
        vob = self._cc_exec(['ls', '-l', '-r', '-vob'])
        vob = re.findall('^(version.*)', vob, re.M)
        fileversions = map(lambda ss: re.match('version\s+([^\s]+)', ss).group(1).replace('\\','/'), vob)
        vobdict = {}
        for fv in fileversions:
            obj = re.match('[\./]*(.+)@@(.+)', fv, re.M)
            vobdict[obj.group(1)] = obj.group(2)
        return vobdict

    def historyBlob(self, since, folderList):
        self.printSignature(since, str(folderList))
        lsh = ['lsh', '-fmt', '%o%m\001%Nd\001%u\001%En\001%Vn\001%Nc\002', '-recurse', '-since', since]
        lsh.extend(folderList) ## To filter our folders specified in configuration
        return self._cc_exec(lsh)

    def copyVobFile(self, ccfile, dest):
        self.printSignature(ccfile, dest)
        self._cc_exec(['get','-to', dest, ccfile])
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IWRITE)

    def undoCheckout(self, file):
        self.printSignature(file)
        self._cc_exec(['unco', '-rm', file])

    def update(self):
        self.printSignature()
        self._cc_exec(['update'])

    def checkin(self, file, comment):
        self.printSignature(file, comment)
        self._cc_exec(['ci', '-identical', '-c', comment, file])

    def checkout(self, file):
        self.printSignature(file)
        self._cc_exec(['co', '-reserved', '-nc', file])


    
    def _cc_exec(self, cmd, **args):
        return popen('cleartool', cmd, self.cc_dir, **args)





