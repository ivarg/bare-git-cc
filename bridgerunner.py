from sys import argv
import traceback
import bridge
import logging
import logging.handlers
import util
import optparse

desc = 'A Git-Clearcase bridge aimed to synchronize between a designated area in a Cleacase snapshot view and a corresponding bare git repository.'
usage = '%prog [-c PATH] tocc|togit|update'


def initLogging(cfg):
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter('> %(message)s'))
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)

    logger = logging.getLogger('log.bgcc.file')
    h = logging.handlers.RotatingFileHandler(cfg.logFile(), maxBytes=130000, backupCount=1)
    h.setFormatter(logging.Formatter('%(asctime)s [%(module)s.%(funcName)s] %(message)s'))
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)

    ## Log errors to email recipient
    h = logging.handlers.SMTPHandler(cfg.smtpServer(), cfg.emailSender(), cfg.emailRecipients(), 'Bridge error alert!')
    h.setFormatter(logging.Formatter('%(message)s'))
    h.setLevel(logging.ERROR)
    # logger.addHandler(h)




def printUsage():
    print 'You need to specify an action: [tocc|togit|update]'

def main():
    parser = optparse.OptionParser(description=desc, usage=usage)
    parser.add_option('-c', '--config', metavar='PATH', action='store', type='string', dest='config', help='Let\'s you rovide a custom path to a configuration file')
    options, args = parser.parse_args()
    if len(args) < 1:
        printUsage()
        exit(1)

    cfg = util.GitConfigParser(options.config)
    initLogging(cfg)
    logger = logging.getLogger('log.bgcc.file')
    logger.info('Git repository at: %s', cfg.gitRoot())
    logger.info('Clearcase view at: %s', cfg.ccRoot())
    bb = bridge.GitCCBridge(cfg)
    try:
        if args[0] == 'tocc':
            bb.onDoCheckinToClearcase()
        if args[0] == 'align':
            bb._addDiscoveredChanges()
        elif args[0] == 'togit':
            # if bridge.isPendingClearcaseChanges():
            bb.onNewClearcaseChanges()
        elif args[0] == 'init':
            bb.newBridge(args[1])
        elif args[0] == 'clone':
            bb._addccfilestogitrepo(args[1])
        elif args[0] == 'update':
            if not bridge.cc.needUpdate():
                logger.info('Clearcase view is up to date')
            else:
                logger.info('Updating Clearcase view')
                bridge.cc.update()
        else:
            printUsage()
            exit(1)
    except bridge.MergeConflictException as mce:
        logger.error('Error: Could not merge commit %s onto branch %s\n   %s' % mce.args)
        traceback.print_exc()
    except bridge.CheckoutReservedException as cre:
        logger.error('Error: Could not checkout files [%s]\n   %s' % cre.args)
        traceback.print_exc()
    except bridge.UpdateCCAreaException as uae:
        logger.error('Error: Could not update files for commit %s\n   %s' % uae.args)
        traceback.print_exc()
    except Exception as e:
        logger.error('Something unexpected has happened: %s', str(e))
        traceback.print_exc()


if __name__ == '__main__':
    main()
    # init()