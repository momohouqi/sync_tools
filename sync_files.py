"""Sync files from src to dst
I use it to sync files from windows to linux.
Rules:
    1.The file will be copy from src to dst if:
        dst file doesn't exists;
        src file new then dst;
    2. The file will not be copy:
        the opposite side of rule 1.
        the src's mtime == its src's mtime of last sync
Usages:
    1. --file <setting_file_of_each_line_is_src:::dst>
    2. --src <src> --dest <dst>


"""
import os, sys, tempfile
import shutil
import logging
import shelve
import argparse

class SyncFiles:
    """src and dst maybe file or dir"""
    def __init__(self, src = "", dst = "", setting_file = ""):
        self._init_log()
        if (src or dst) and setting_file:
            logging.error("--src, --dst can't be with --file")
            sys.exit(-1)

        self._src = src
        self._dst = dst
        self._setting_file = setting_file

        self._init_shelve()

    def _init_log(selfs):
        LOG_FORMAT = "[%(levelname)s] %(message)s"
        logging.basicConfig(level=logging.INFO, format = LOG_FORMAT)

    def _init_shelve(self):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        self._shelve = shelve.open(os.path.join(current_dir, ".sync.shelve"), flag = "c")

    def sync(self):
        if self._setting_file:
            return self._sync_by_setting_file()
        else:
            return self._sync(self._src, self._dst)

    def _sync_by_setting_file(self):
        if not os.path.exists(self._setting_file):
            logging.error("[Error] setting file doesn't exist:{0}".format(self._setting_file))
            return -1

        with open(self._setting_file, "r") as f:
            for line in f.readlines():
                src, dst = line.strip().split(":::")
                self._sync(src, dst)

        return 0


    def _sync(self, src, dst):
        src_to_dst = {}
        for path in src.split(","):
            path = os.path.abspath(path)
            if os.path.isfile(path):
                dst_file = dst if os.path.isfile(dst) else os.path.join(dst, os.path.basename(path))
                src_to_dst[path] = dst_file
            elif os.path.isdir(path):
                for f in os.listdir(path):
                    src_file = os.path.join(path, f)
                    dst_file = dst if os.path.isfile(dst) else os.path.join(dst, f)
                    src_to_dst[src_file] = dst_file
            else:
                logging.warning("[Warning] Not exist: {0}".format(path))

        for src, dst in src_to_dst.items():
            self._sync_one_file(src, dst)

        return 0

    def _sync_one_file(self, src, dst):
        from datetime import datetime
        last_sync_mtime_str = self._shelve.get(src, "")
        current_mtime_str = os.path.getmtime(src)
        if last_sync_mtime_str != current_mtime_str:
            if os.path.exists(dst):
                timedelta = datetime.fromtimestamp(current_mtime_str) - datetime.fromtimestamp(os.path.getmtime(dst))
                need_update = timedelta.seconds > 1
                if not need_update:
                    logging.debug("dst,src mtime same , skipped")
            else:
                need_update = True
        else:
            need_update = False
            logging.debug("mtime not change, skipped")

        if need_update:
            shutil.copy2(src, dst)
            self._shelve[src] = current_mtime_str
            logging.info("[SyncOK] sync file successfully: {0}".format(os.path.basename(src)))
        else:
            logging.info("[Skipped] the modified time is the same, skipped: '{0}' ".format(os.path.basename(src)))

def main():
    parser = argparse.ArgumentParser(description="Sync files by modified time")

    parser.add_argument("--src",dest="src", type=str, help = "files or paths, devided by ','")
    parser.add_argument("--dst",dest="dst", type=str, help = "file or dir, destination path")
    parser.add_argument("--file", dest="file", type = str, help = "each line of the file is src:::dst")

    options = parser.parse_args()

    sync_files = SyncFiles(src = options.src, dst = options.dst, setting_file = options.file)
    return sync_files.sync()


if __name__ == '__main__':
    sys.exit(main())