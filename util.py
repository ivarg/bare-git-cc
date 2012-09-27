import os
import os.path
from subprocess import Popen, PIPE
from os.path import join, dirname, exists
from ConfigParser import SafeConfigParser
import inspect
import logging
from datetime import datetime

logger = logging.getLogger('log.bgcc.file')

# cfg = None

# def readConfiguration(file=None):
    # logger.warning('read configuration')
    # global cfg
    # cfg = GitConfigParser(file)


class GitConfigParser():
    def __init__(self, configFile=None):
        logger.debug('')
        cwd = os.getcwd()
        if configFile:
            self.file = configFile
        elif exists(join(cwd, 'bgcc.conf')):
            self.file = join(cwd, 'bgcc.conf')
        elif exists(join(cwd, '.git', 'bgcc.conf')):
            self.file = join(cwd, 'bgcc.conf')
        else:
            raise Exception('No configuration file found')
        self.parser = SafeConfigParser()
        self.parser.read(self.file)

    def gitRoot(self):
        gitroot = self.parser.get('core', 'git_root')
        return gitroot
    def ccRoot(self):
        ccroot = self.parser.get('core', 'cc_root')
        return ccroot
    def logFile(self):
        return self.parser.get('core', 'log_file')
    def remote(self):
        if self.parser.has_option('core', 'remote'):
            return self.parser.get('core', 'remote')
        return None
    def getInclude(self):
        return self.parser.get('core', 'include').split('|')
    def getBranches(self):
        return self.parser.get('core', 'branches').split('|')
    def emailSender(self):
        return self.parser.get('email', 'sender')
    def emailRecipients(self):
        return self.parser.get('email', 'recipients').split('|')
    def smtpServer(self):
        return self.parser.get('email', 'smtp')
    def recursive(self):
        if self.parser.has_option('core', 'recursive'):
            return self.parser.get('core', 'recursive') == 'True'
        return True


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


def timeDiff(t1, t2):
    # The assumption is that t2 > t1
    t1 = datetime.strptime(t1, '%Y%m%d.%H%M%S')
    t2 = datetime.strptime(t2, '%Y%m%d.%H%M%S')
    td = t2 - t1
    return td.days*24*60*60 + td.seconds

