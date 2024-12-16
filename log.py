import logging
import sys

LOG_FORMATTER = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")


def getLogger(name):
    """
        获取一个日志管理对象
    @param name: 对象名称
    @return:
    """
    logger = logging.getLogger(name)

    file_handler = logging.FileHandler("{0}/{1}.log".format("./", name))
    file_handler.setFormatter(LOG_FORMATTER)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(LOG_FORMATTER)
    logger.addHandler(console_handler)

    logger.setLevel(logging.DEBUG)
    return logger
