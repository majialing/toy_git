# 用 python 实现自己的 Git：toy_git



参考大神的[仓库](https://github.com/benhoyt/pygit)和[文章](https://benhoyt.com/writings/pygit/)比较彻底的学习了 Git 的原理。在自己的代码中实现了 git init、add、commit、push 这几个基本操作。



## 介绍

当前目录的 `toy_git.ipynb` 是翻译后的文章，但是要完全实现 git init、add、commit、push 这些操作必须要参考大神的代码。我把我自己写的代码放在了 `code` 文件夹方便学习与参考。`image` 文件夹中放了一些图片。



整个学习并不复杂，跟着文章的思路以及代码就能实现。



**如果你也想实现一个 toy_git 的话，可以先看 toy_git.ipynb 里面的内容，然后看着 code 里面的代码，按照 init add commit push 的顺序来**。



![](https://github.com/TensShinet/toy_git/blob/master/image/toy_git.png?raw=true)






## 如何使用 toy_git.py

**python3.6+ ubuntu18.04**

+ 在 GitHub 上面创建一个空仓库

  ![](https://github.com/TensShinet/toy_git/blob/master/image/empty_remote_repo.png?raw=true)

  

+ **创建一个空文件夹**

  ![](https://github.com/TensShinet/toy_git/blob/master/image/empty_repo.png?raw=true)

  

+ **将 toy_git.py 放入这个文件夹中并创建 user.py**

  ![](https://github.com/TensShinet/toy_git/blob/master/image/files.png?raw=true)

+ **由于实现的 git push 用的是 https 不是 ssh，所以需要账号和密码，写入 user.py 中**

  ![](https://github.com/TensShinet/toy_git/blob/master/image/user.png?raw=true)

+ **运行 python3 toy_git.py**

![](https://github.com/TensShinet/toy_git/blob/master/image/result.png?raw=true)



+ [结果](https://github.com/TensShinet/test_repo)



## 最后

扫个码我们做朋友吧！***\*顺便点个 star 呗！\****

![](https://github.com/TensShinet/learn_statistical-learning-method/blob/master/images/wx.png?raw=true)