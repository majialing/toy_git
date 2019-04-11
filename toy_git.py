import collections, hashlib, os


def write_file(path, data):
    with open(path, 'wb') as f:
        f.write(data)

class ToyGit():
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
        

def main():
    tg = ToyGit()
    tg.init('/home/tenshine/Desktop/toy_git/test_repo')


if __name__ == "__main__":
    main()
