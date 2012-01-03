from sys import argv
import traceback
import bridge
import logging
import logging.handlers
import util


def setupRootLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter('%(message)s'))
    h.setLevel(logging.INFO)
    logger.addHandler(h)

    h = logging.handlers.RotatingFileHandler(bridge.LOG_FILE, maxBytes=32768, backupCount=1)
    h.setFormatter(logging.Formatter('%(asctime)s [%(module)s.%(funcName)s] %(message)s'))
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)

    h = logging.handlers.SMTPHandler('10.254.66.32', 'bare-git-cc@sungard.com', ['ivar.gaitan@sungard.com'], 'Bridge error alert!')
    h.setFormatter(logging.Formatter('%(message)s'))
    h.setLevel(logging.ERROR)
    logger.addHandler(h)


setupRootLogger()
logger = logging.getLogger()

if __name__ == '__main__':
    bb = bridge.GitCCBridge()

    if argv[1] == 'checkin':
        try:
            bb.onDoCheckinToClearcase()
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

    elif argv[1] == 'fetch_cc':
        try:
            if bridge.isPendingClearcaseChanges():
                bb.onNewClearcaseChanges()
        except Exception as e:
            logger.error('Something unexpected has happened: %s', str(e))
            traceback.print_exc()

