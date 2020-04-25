#操作步骤：

1、添加文件夹data、checkpoints  

2、下载数据，解压后将三个.csv直接放入到data文件夹下，连接地址：https://pan.baidu.com/s/1TprekQac-yzNHMsREWZe9g，Code: uhxt 

![data](https://github.com/YourPeer/classification-nlp/blob/master/readme_images/0.png)  

3、下载预训练词向量（链接：https://pan.baidu.com/s/1svFOwFBKnnlsqrF1t99Lnw），使用bunzip2 FileName.bz2解压该文件（windows下使用git bash解压，cmd解压不了）。  

![checkpoints](https://github.com/YourPeer/classification-nlp/blob/master/readme_images/1.png)
  
4、运行train.py即可，参数调整在args.py,模型调整在model.py  

5、train完模型保存至output_dir文件夹下，词向量模型保存至data文件夹下
