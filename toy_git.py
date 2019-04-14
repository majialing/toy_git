import collections, hashlib, os, struct
import zlib, time, subprocess


# git index (.git/index) 里面的一个入口
IndexEntry = collections.namedtuple('IndexEntry', [
    'ctime_s', 'ctime_n', 'mtime_s', 'mtime_n', 'dev', 'ino', 'mode', 'uid',
    'gid', 'size', 'sha1', 'flags', 'path',
])

def write_file(path, data):
    with open(path, 'wb') as f:
        f.write(data)

def read_file(path):
    with open(path, 'rb') as f:
        return f.read()


def read_index(path):
    entrys = []
    return entrys

class ToyGit():
    def __init__(self, root):
        self.root = root
        self.git = os.path.join(root, '.git')

    def init(self, repo_path):
        """
        创建多个目录，以及 HEAD 文件
        1. .git
        2. .git 下 objects refs refs/heads 目录
        3. HEAD 文件 b'ref: refs/heads/master'
        """
        e = os.path.exists(os.path.join(repo_path, '.git'))
        if e:
            print('repository exists: {}'.format(repo_path))
            return
        os.mkdir(os.path.join(repo_path, '.git'))
        dirs = ['objects', 'refs', 'refs/heads']
        for d in dirs:
            os.mkdir(os.path.join(repo_path, '.git', d))
        write_file(os.path.join(repo_path, '.git', 'HEAD'), b'ref: refs/heads/master')
        print('initialized empty repository: {}'.format(repo_path))

    def read_index(self):
        """
        1. data[:-20].digest() 等于 data[-20:].digest()
        2. signature(4s)==b'DIRC' version(L)==2 num_entries(L) 存在前 data[:12]
        3. 每个 entry 的开头 有 62 个字节 这 62 个字节存着文件信息(LLLLLLLLLL20sH)
        4. 接下来是文件名，结尾是 b'\x00'
        5. 文件名后面是 n 个 b'\x00' 这 n 个用来凑 8 的倍数
        """
        try:
            data = read_file(os.path.join(self.git, 'index'))
        except FileNotFoundError:
            return []

        digest = hashlib.sha1(data[:-20]).digest()
        assert digest == data[-20:], 'error index'
        header = data[:12]
        signature, version, num_entries = struct.unpack('!4sLL', header)
        assert signature == b'DIRC', 'error signature'
        assert version == 2, 'error version'
        entry_data = data[12:-20]
        entrys = []
        i = 0

        while(i + 62 < len(entry_data)):
            header_end = i + 62
            entry_header = entry_data[i:header_end]
            # 获得 entry 头
            header = struct.unpack('!LLLLLLLLLL20sH', entry_header)
            # 获得文件名，找到 b'\x00'
            path_end = entry_data.index(b'\x00', header_end)
            path = entry_data[header_end:path_end]
            entry = IndexEntry(*(header + (path.decode(),)))
            entrys.append(entry)
            entry_len = (62 + len(path) + 8) // 8 * 8
            i += entry_len
        return entrys

    def hash_object(self, data, obj_type, write=True):
        """
        在 objects 里面写入文件
        有三种格式 
        1. blob 普通文件
        2. tree
        3. commit 
        """
        header = '{} {}'.format(obj_type, len(data)).encode()
        full_data = header + b'\x00' + data
        sha1 = hashlib.sha1(full_data).hexdigest()
        if write:
            path = os.path.join('.git', 'objects', sha1[:2], sha1[2:])
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                write_file(path, zlib.compress(full_data))
        return sha1

    def write_index(self, entrys):
        """
        1. 头部前 12 个字符
        2. 尾部是由 前面的所有字符 hashlib.sha1() 得来的
        3. 中间是每一个 entry 连续放在一起。每个 entry 有 62 个字节的头，LLLLLLLLLL20sH
            然后是 path 最后是填充的 b'\x00' 长度要是 8 的倍数
            如果 entry + path 长度是 8 的倍数那么添加 8 个 b'\x00'
            这里有一个小技巧 可以看我的博客
            https://www.jianshu.com/p/570b61384720
        """
        signature, version, num_entries = b'DIRC', 2, len(entrys)
        header = struct.pack('!4sLL', signature, version, num_entries)
        packed_entrys = []
        for entry in entrys:
            entry_head = struct.pack('!LLLLLLLLLL20sH',
                entry.ctime_s, entry.ctime_n, entry.mtime_s, entry.mtime_n,
                entry.dev, entry.ino, entry.mode, entry.uid, entry.gid,
                entry.size, entry.sha1, entry.flags)
            path = entry.path.encode()
            length = ((62 + len(path) + 8) // 8) * 8
            packed_entry = entry_head + path + b'\x00' * (length - 62 - len(path))
            packed_entrys.append(packed_entry)
        all_data = header + b''.join(packed_entrys)
        digest = hashlib.sha1(all_data).digest()
        all_data += digest
        write_file(os.path.join(self.git, 'index'), all_data)
    
    def write_tree(self):
        """
            把当前的 index 写入树中
            写法与普通文件一样，
            tree_entry mode_path + b'\x00' + index 的 entry.sha1
            model_path = '{:o} {}'.format(entry.mode, entry.path)
        """
        tree_entrys = []
        for entry in self.read_index():
            assert '/' not in entry.path, \
                'currently only supports a single, top-level directory'
            model_path = '{:o} {}'.format(entry.mode, entry.path).encode()
            tree_entry = model_path + b'\x00' + entry.sha1
            tree_entrys.append(tree_entry)

        return self.hash_object(b''.join(tree_entrys), 'tree')


    def add(self, file_paths):
        """
        只支持文件 不支持目录和 .
        而且只支持根目录的文件

        1. 标准化路径不能有 \\
        2. 读取所有的索引
        3. 生成新的索引
        4. 索引按 path 排序
        5. 写入新的索引
        """
        paths = [p.replace('\\', '/') for p in file_paths]
        all_entrys = self.read_index()
        entrys = [e for e in all_entrys if e.path not in paths]
        for path in paths:
            real_path = os.path.join(self.root, path)
            sha1 = self.hash_object(read_file(real_path), 'blob')
            st = os.stat(real_path)
            flags = len(path.encode())
            assert flags < (1 << 12)
            entry = IndexEntry(
                int(st.st_ctime), 0, int(st.st_mtime), 0, st.st_dev,
                st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_size,
                bytes.fromhex(sha1), flags, path)
            entrys.append(entry)
        entrys.sort(key=lambda x: x.path)
        self.write_index(entrys)

    def get_local_master_hash(self):
        """
        得到 master
        """
        master_path = os.path.join('.git', 'refs', 'heads', 'master')
        try:
            return read_file(master_path).decode().strip()
        except FileNotFoundError:
            return None

    def commit(self, message, author=None):
        """
        提交：
        1. 把当前 index 写入树中
        2. 得到当前仓库 master 在 ./git/refs/heads/master 中
        3. 讲所有的数据放在一起 [上一个 master, author, committer, '', messge, '']
        4. 将这些内容通过 hash_object 写入 objects 文件夹中 commit
        """
        tree = self.write_tree()
        parent = self.get_local_master_hash()
        if author is None:
            author = '{} <{}>'.format(
                subprocess.run(['git', 'config', '--global', 'user.name'], stdout=subprocess.PIPE).stdout.decode().strip(), 
                subprocess.run(['git', 'config', '--global', 'user.email'], stdout=subprocess.PIPE).stdout.decode().strip())
        
        timestamp = int(time.mktime(time.localtime()))
        utc_offset = -time.timezone
        # 提交时间，我实在不是很理解他是怎么得到的，所以就抄了
        author_time = '{} {}{:02}{:02}'.format(
                timestamp,
                '+' if utc_offset > 0 else '-',
                abs(utc_offset) // 3600,
                (abs(utc_offset) // 60) % 60)

        lines = ['tree ' + tree]
        if parent:
            lines.append('parent ' + parent)
        lines.append('author {} {}'.format(author, author_time))
        lines.append('committer {} {}'.format(author, author_time))
        lines.append('')
        lines.append(message)
        lines.append('')
        data = '\n'.join(lines).encode()
        sha1 = self.hash_object(data, 'commit')
        master_path = os.path.join('.git', 'refs', 'heads', 'master')
        write_file(master_path, (sha1 + '\n').encode())
        print('committed to master: {:7}'.format(sha1))
        return sha1


        

def main():
    tg = ToyGit('/home/tenshine/Desktop/toy_git/test_repo')
    tg.init(os.path.join(tg.root))
    # tg.read_index()
    tg.add(['test.py'])
    tg.commit('提交 test.py')

if __name__ == "__main__":
    main()
