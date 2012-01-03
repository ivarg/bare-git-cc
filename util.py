import os
import os.path
from subprocess import Popen, PIPE
from os.path import join, dirname, exists
from ConfigParser import SafeConfigParser
import inspect
import logging

logger = logging.getLogger()


class Loggable(object):
    def printSignature(self, *args):
        cname = self.__class__.__name__
        fname = inspect.getouterframes(inspect.currentframe())[1][3]
        alist = ','.join(args)
        logger.log(logging.DEBUG-1, '%s.%s(%s)' % (cname, fname, alist))


class GitConfigParser():
    CORE = 'core'
    def __init__(self, git_dir, branch):
        self.section = branch
        self.file = join(git_dir, '.git', 'gitcc')
        self.parser = SafeConfigParser();
        self.parser.add_section(self.section)
    def set(self, name, value):
        self.parser.set(self.section, name, value)
    def read(self):
        self.parser.read(self.file)
    def write(self):
        self.parser.write(open(self.file, 'w'))
    def getCore(self, name, *args):
        return self._get(self.CORE, name, *args)
    def get(self, name, *args):
        return self._get(self.section, name, *args)
    def _get(self, section, name, default=None):
        if not self.parser.has_option(section, name):
            return default
        return self.parser.get(section, name)
    def getList(self, name, default=None):
        return self.get(name, default).split('|')
    def getInclude(self):
        return self.getCore('include', '.').split('|')
    def getBranches(self):
        return self.getList('branches', 'main')
    def getExtraBranches(self):
        return self.getList('_branches', 'main')


def prepareForCopy(filepath):
    if os.path.exists(filepath):
        os.remove(filepath)
    else:
        try:
            os.makedirs(os.path.dirname(filepath))
        except os.error:
            pass # The directory already exists


def popen(exe, cmd, cwd, env=None, decode=True, errors=True):
    cmd.insert(0, exe)
    f = lambda a: a if not a.count(' ') else '"%s"' % a
    logger.log(logging.DEBUG-5, ' '.join(map(f, cmd)))
    pipe = Popen(cmd, cwd=cwd, stdout=PIPE, stderr=PIPE, env=env)
    (stdout, stderr) = pipe.communicate()
    if errors and pipe.returncode > 0:
        raise Exception((stderr + stdout))
    return stdout if not decode else stdout
