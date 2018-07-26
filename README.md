# sync_tools
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
