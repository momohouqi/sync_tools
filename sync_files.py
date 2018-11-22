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
import re
from datetime import datetime
from collections import OrderedDict


class SettingFile:
    """Setting file parser"""
    FROM = "FROM"
    TO = "TO"
    GROUP_KEY = "Group"
    GLOBAL_GROUP = "global"

    def __init__(self, setting_file, groups=""):
        self._setting_file = setting_file
        self._vars = None
        self._groups = groups

    @classmethod
    def is_group_line(cls, line):
        return line.strip().lower().startswith(cls.GROUP_KEY.lower() + ":")

    @classmethod
    def is_comment_out_line(cls, line):
        return line.strip().startswith('//')

    @classmethod
    def is_assignment_line(cls, line):
        return '=' in line

    def get_defined_vars(self, var_name):
        if self._vars is None:
            self._vars = {}
            with open(self._setting_file, 'r') as f:
                for line in f.readlines():
                    line = line.strip()
                    if not self.is_comment_out_line(line) and self.is_assignment_line(line):
                        name, value = line.split('=')
                        if name and value:
                            self._vars[name] = value

        return self._vars[var_name].strip()

    def _replace_var_with_value(self, line):
        def get_var_pattern(line):
            return re.search("\$[a-zA-Z_]+", line)

        var_pattern = get_var_pattern(line)
        while var_pattern:
            var = var_pattern.group(0)[1:]
            line = line.replace('$' + var, self.get_defined_vars(var))
            var_pattern = get_var_pattern(line)
        return line

    def _handle_groups(self):
        """Return a OrderedMap: {groupName:[line0, line1,...]}"""
        groups = OrderedDict()
        group_name = self.GLOBAL_GROUP
        with open(self._setting_file, "r") as f:
            for line in f.readlines():
                line = line.strip()
                if self.is_group_line(line):
                    group_name = line.split(':')[1]
                    continue

                #if not line or self.is_comment_out_line(line) or self.is_assignment_line(line):
                if not line or self.is_comment_out_line(line):
                    continue
                g = groups.get(group_name, [])
                g.append(line)
                groups[group_name] = g
        return groups

    def get_src_dst_pairs(self):
        def handle_pair_flag_in_line(line):
            line = self._replace_var_with_value(line)
            src, dst = line.strip().split(":::")
            return src, dst

        def handle_only_src_in_line(line):
            src = line
            from_path = self.get_defined_vars(self.FROM)
            port = self.get_defined_vars(self.TO)
            if not line.lower().startswith(from_path.lower()):
                raise Exception("Wrong line:{}".format(line))
            #dst = os.path.join(port, 'app', line[len(from_path):])
            dst1 = port + "\\" + line[len(from_path):]
            return src, dst1

        src2dst = {}
        groups = self._handle_groups()

        allowed_groups = self._groups.split(',')
        if self.GLOBAL_GROUP not in allowed_groups:
            allowed_groups.insert(0, self.GLOBAL_GROUP)

        for group_name, lines in groups.items():
            # empty allowed all groups
            if group_name in allowed_groups:
                for line in lines:
                    line = line.strip()
                    if not line or self.is_comment_out_line(line) or self.is_assignment_line(line):
                        continue
                    if ':::' in line:
                        src, dst = handle_pair_flag_in_line(line)
                    else:
                        src, dst = handle_only_src_in_line(line)
                        print "===src:{}, dst:{}".format(src, dst)

                    src2dst[src] = dst
        return src2dst


class SyncFiles:
    """src and dst maybe file or dir"""
    def __init__(self, src = "", dst = "", setting_file = "", force = False, groups=""):
        self._init_log()
        if (src or dst) and setting_file:
            logging.error("--src, --dst can't be with --file")
            sys.exit(-1)

        self._src = src
        self._dst = dst
        self._setting_file_parser = None
        self._force_copy = force

        self._vars = {}

        if setting_file:
            self._setting_file_parser = SettingFile(setting_file, groups)

        self._init_shelve()
        self._sync_success_count = 0
        self._skipped_sync_count = 0

    def _init_log(selfs):
        LOG_FORMAT = "[%(levelname)s] %(message)s"
        logging.basicConfig(level=logging.INFO, format = LOG_FORMAT)

    def _init_shelve(self):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        self._shelve = shelve.open(os.path.join(current_dir, ".sync.shelve"), flag = "c")

    def _print_statistics(self):
        logging.info('===>Sync:{0}; Skipped:{1}\n'.format(self._sync_success_count, self._skipped_sync_count))

    def sync(self):
        try:
            if self._setting_file_parser:
                return self._sync_by_setting_file()
            else:
                return self._sync(self._src, self._dst)
        finally:
            self._print_statistics()

    def _sync_by_setting_file(self):
        src2dst = self._setting_file_parser.get_src_dst_pairs()
        for src, dst in src2dst.items():
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
        logging.debug("sync file: " + src + " to " + dst)

        current_mtime_str = os.path.getmtime(src)
        if not self._force_copy:
            last_sync_mtime_str = self._shelve.get(src, "")
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
        else:
            need_update = True

        if need_update:
            shutil.copy2(src, dst)
            self._shelve[src] = current_mtime_str
            logging.info("[SyncOK] sync file successfully: {0}".format(os.path.basename(src)))
            self._sync_success_count += 1
        else:
            logging.info("[Skipped] the modified time is the same, skipped: '{0}' ".format(os.path.basename(src)))
            self._skipped_sync_count += 1

def main():
    parser = argparse.ArgumentParser(description="Sync files by modified time")

    parser.add_argument("--src",dest="src", type=str, help = "files or paths, devided by ','")
    parser.add_argument("--dst",dest="dst", type=str, help = "file or dir, destination path")
    parser.add_argument("--file", dest="file", type = str, help = "each line of the file is src:::dst")
    parser.add_argument("--force", dest="force", action="store_true", help = "force copy ignore the mtime")
    parser.add_argument("--group", dest="groups", type=str, help = "specify the sync groups, separated by comma", default="")

    options = parser.parse_args()

    sync_files = SyncFiles(src = options.src, dst = options.dst,
                           setting_file = options.file, force = options.force, groups=options.groups)
    return sync_files.sync()


if __name__ == '__main__':
    sys.exit(main())