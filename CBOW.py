#!/usr/bin/env python
# coding: utf-8

# In[1]:


import io
import os
import sys
import requests
from collections import OrderedDict 
import math
import random
import numpy as np
import paddle
import paddle.fluid as fluid
from paddle.fluid.dygraph.nn import Embedding


# In[2]:


#下载语料用来训练word2vec
def download():
    #可以从百度云服务器下载一些开源数据集（dataset.bj.bcebos.com）
    corpus_url = "https://dataset.bj.bcebos.com/word2vec/text8.txt"
    #使用python的requests包下载数据集到本地
    web_request = requests.get(corpus_url)
    corpus = web_request.content
    #把下载后的文件存储在当前目录的text8.txt文件内
    with open("./text8.txt", "wb") as f:
        f.write(corpus)
    f.close()
download()


# In[3]:


#读取text8数据
def load_text8():
    with open("./text8.txt", "r") as f:
        corpus = f.read().strip("\n")
    f.close()
    return corpus
corpus = load_text8()
#打印前500个字符，简要看一下这个语料的样子
print(corpus[:500])


# In[4]:


#对语料进行预处理（分词）
def data_preprocess(corpus):
    #由于英文单词出现在句首的时候经常要大写，所以我们把所有英文字符都转换为小写，
    #以便对语料进行归一化处理（Apple vs apple等）
    corpus = corpus.strip().lower()
    corpus = corpus.split(" ")
    return corpus
corpus = data_preprocess(corpus)
print(corpus[:50])


# In[5]:


#构造词典，统计每个词的频率，并根据频率将每个词转换为一个整数id
def build_dict(corpus):
    #首先统计每个不同词的频率（出现的次数），使用一个词典记录
    word_freq_dict = dict()
    for word in corpus:
        if word not in word_freq_dict:
            word_freq_dict[word] = 0
        word_freq_dict[word] += 1
    #将这个词典中的词，按照出现次数排序，出现次数越高，排序越靠前
    #一般来说，出现频率高的高频词往往是：I，the，you这种代词，而出现频率低的词，往往是一些名词，如：nlp
    word_freq_dict = sorted(word_freq_dict.items(), key = lambda x:x[1], reverse = True)
    #构造3个不同的词典，分别存储，
    #每个词到id的映射关系：word2id_dict
    #每个id出现的频率：word2id_freq
    #每个id到词典映射关系：id2word_dict
    word2id_dict = dict()
    word2id_freq = dict()
    id2word_dict = dict()
    #按照频率，从高到低，开始遍历每个单词，并为这个单词构造一个独一无二的id
    for word, freq in word_freq_dict:
        curr_id = len(word2id_dict)
        word2id_dict[word] = curr_id
        word2id_freq[word2id_dict[word]] = freq
        id2word_dict[curr_id] = word
    return word2id_freq, word2id_dict, id2word_dict
word2id_freq, word2id_dict, id2word_dict = build_dict(corpus)
vocab_size = len(word2id_freq)
# print("there are totoally %d different words in the corpus" % vocab_size)
# for _, (word, word_id) in zip(range(50), word2id_dict.items()):
#     print("word %s, its id %d, its word freq %d" % (word, word_id, word2id_freq[word_id]))


# In[6]:


#将文章换成ID
data=[]
for i in corpus:
    id=word2id_dict[i]
    data.append(id)
print(data[:5])


# In[7]:


#构造数据，准备模型训练
#bag_size代表了单侧已知词汇数
#negative_sample_num代表了对于每个正样本，我们需要随机采样多少负样本用于训练，
#一般来说，negative_sample_num的值越大，训练效果越稳定，但是训练速度越慢。 
def build_data(data, word2id_dict, word2id_freq, bag_size=3, negative_sample_num = 4):
    #使用一个list存储处理好的数据
    dataset = []
    #从左到右，开始移动窗口
    for i in range(len(corpus)):
        if i<=len(data)-2*bag_size-1: 
            front=data[i:i+bag_size]
            back=data[i+bag_size+1:i+2*bag_size+1]
            span=front+back
            #以max_window_size为上限，随机采样一个window_size，这样会使得训练更加稳定
            # window_size = random.randint(1, max_window_size)
        # #当前的中心词就是center_word_idx所指向的词
        # center_word = corpus[center_word_idx]
            positive_word=data[i+bag_size]
            #首先把（中心词，正样本，label=1）的三元组数据放入dataset中，
            #这里label=1表示这个样本是个正样本
            dataset.append((span, positive_word, 1))
            #开始负采样
            i = 0
            while i < negative_sample_num:
                negative_word= random.randint(0, vocab_size-1)
                if negative_word != positive_word:
                    #把（中心词，正样本，label=0）的三元组数据放入dataset中，
                    #这里label=0表示这个样本是个负样本
                    dataset.append((span, negative_word, 0))
                    i += 1
    return dataset

dataset = build_data(data, word2id_dict, word2id_freq)
print(dataset[:5])


# In[8]:


#构造mini-batch，准备对模型进行训练
#我们将不同类型的数据放到不同的tensor里，便于神经网络进行处理
#并通过numpy的array函数，构造出不同的tensor来，并把这些tensor送入神经网络中进行训练
def build_batch(dataset, batch_size, epoch_num):
    #span_batch缓存batch_size个
    span_batch = []
    #target_word_batch缓存batch_size个目标词（可以是正样本或者负样本）
    target_word_batch = []
    #label_batch缓存了batch_size个0或1的标签，用于模型训练
    label_batch = []
    for epoch in range(epoch_num):
        #每次开启一个新epoch之前，都对数据进行一次随机打乱，提高训练效果
        random.shuffle(dataset)
        for span, target_word, label in dataset:
            #遍历dataset中的每个样本，并将这些数据送到不同的tensor里
            span_batch.append(span)
            target_word_batch.append([target_word])
            label_batch.append(label)
            #当样本积攒到一个batch_size后，我们把数据都返回回来
            #在这里我们使用numpy的array函数把list封装成tensor
            #并使用python的迭代器机制，将数据yield出来
            #使用迭代器的好处是可以节省内存
            if len(span_batch) == batch_size:
                yield np.array(span_batch).astype("int64"),                     np.array(target_word_batch).astype("int64"),                     np.array(label_batch).astype("float32")
                span_batch = []
                target_word_batch = []
                label_batch = []

    if len(span_batch) > 0:
        yield np.array(span_batch).astype("int64"),             np.array(target_word_batch).astype("int64"),             np.array(label_batch).astype("float32")

# for _, batch in zip(range(10), build_batch(dataset, 128, 3)):
#     print(batch)


# In[9]:


#定义CBOW训练网络结构
#这里我们使用的是paddlepaddle的1.6.1版本
#一般来说，在使用fluid训练的时候，我们需要通过一个类来定义网络结构，这个类继承了fluid.dygraph.Layer
class CBOW(fluid.dygraph.Layer):
    def __init__(self, name_scope, vocab_size, embedding_size, init_scale=0.1):
        #name_scope定义了这个类某个具体实例的名字，以便于区分不同的实例（模型）
        #vocab_size定义了这个skipgram这个模型的词表大小
        #embedding_size定义了词向量的维度是多少
        #init_scale定义了词向量初始化的范围，一般来说，比较小的初始化范围有助于模型训练
        super(CBOW, self).__init__(name_scope)
        self.vocab_size = vocab_size
        self.embedding_size = embedding_size

        #使用paddle.fluid.dygraph提供的Embedding函数，构造一个词向量参数
        #这个参数的大小为：[self.vocab_size, self.embedding_size]
        #数据类型为：float32
        #这个参数的名称为：embedding_para
        #这个参数的初始化方式为在[-init_scale, init_scale]区间进行均匀采样
        self.embedding = Embedding(
            self.full_name(),
            size=[self.vocab_size, self.embedding_size],
            dtype='float32',
            param_attr=fluid.ParamAttr(
                name='embedding_para',
                initializer=fluid.initializer.UniformInitializer(
                    low=-0.5/embedding_size, high=0.5/embedding_size)))

        #使用paddle.fluid.dygraph提供的Embedding函数，构造另外一个词向量参数
        #这个参数的大小为：[self.vocab_size, self.embedding_size]
        #数据类型为：float32
        #这个参数的名称为：embedding_para
        #这个参数的初始化方式为在[-init_scale, init_scale]区间进行均匀采样
        #跟上面不同的是，这个参数的名称跟上面不同，因此，
        #embedding_out_para和embedding_para虽然有相同的shape，但是权重不共享
        self.embedding_out = Embedding(
            self.full_name(),
            size=[self.vocab_size, self.embedding_size],
            dtype='float32',
            param_attr=fluid.ParamAttr(
                name='embedding_out_para',
                initializer=fluid.initializer.UniformInitializer(
                    low=-0.5/embedding_size, high=0.5/embedding_size)))

    #定义网络的前向计算逻辑
    #span_batch是一个tensor（mini-batch）
    #target_words_batch是一个tensor（mini-batch），表示目标词
    #label_batch是一个tensor（mini-batch），表示这个词是正样本还是负样本（用0或1表示）
    #用于在训练中计算这个tensor中对应词的同义词，用于观察模型的训练效果
    def forward(self, span_batch, target_words_batch, label_batch):
        #首先，通过embedding_para（self.embedding）参数，将mini-batch中的词转换为词向量
        #这里span_batch和eval_words_emb查询的是一个相同的参数
        #而target_words_emb查询的是另一个参数
        target_words_batch= fluid.dygraph.to_variable(target_words_batch)
        label_batch= fluid.dygraph.to_variable(label_batch)

        span_zero=np.zeros((span_batch.shape[0],self.embedding_size),dtype=np.float32)
        span_emb= fluid.dygraph.to_variable(span_zero)
        span_batch=span_batch.T
        for span in span_batch:
            span=span.reshape(span_batch.shape[1],1)
            span=fluid.dygraph.to_variable(span)
            span_emb_sub= self.embedding(span)
            span_emb=span_emb+span_emb_sub
        # span_emb = fluid.layers.reduce_sum(span_emb, 1)
        target_words_emb = self.embedding_out(target_words_batch)
        #center_words_emb = [batch_size, embedding_size]
        #target_words_emb = [batch_size, embedding_size]
        # print(span_emb)
        # print(target_words_emb)
        #我们通过点乘的方式计算中心词到目标词的输出概率，并通过sigmoid函数估计这个词是正样本还是负样本的概率。
        word_sim = fluid.layers.elementwise_mul(span_emb, target_words_emb)
        word_sim = fluid.layers.reduce_sum(word_sim, dim = -1)
        pred = fluid.layers.sigmoid(word_sim)
        #通过估计的输出概率定义损失函数
        loss = fluid.layers.sigmoid_cross_entropy_with_logits(word_sim, label_batch)
        loss = fluid.layers.reduce_mean(loss)
        #返回前向计算的结果，飞桨会通过backward函数自动计算出反向结果。
        return pred, loss


# In[10]:


#开始训练，定义一些训练过程中需要使用的超参数
batch_size =512
epoch_num = 3
embedding_size = 200
step = 0
learning_rate = 0.001

#定义一个使用word-embedding查询同义词的函数
#这个函数query_token是要查询的词，k表示要返回多少个最相似的词，embed是我们学习到的word-embedding参数
#我们通过计算不同词之间的cosine距离，来衡量词和词的相似度
def get_similar_tokens(query_token, k, embed):
    W = embed.numpy()
    x = W[word2id_dict[query_token]]
    cos = np.dot(W, x) / np.sqrt(np.sum(W * W, axis=1) * np.sum(x * x) + 1e-9)
    flat = cos.flatten()
    indices = np.argpartition(flat, -k)[-k:]
    indices = indices[np.argsort(-flat[indices])]
    for i in indices:
        print('for word %s, the similar word is %s' % (query_token, str(id2word_dict[i])))

#将模型放到GPU上训练（fluid.CUDAPlace(0)），如果需要指定CPU，则需要改为fluid.CPUPlace()
with fluid.dygraph.guard(fluid.CUDAPlace(0)):
    #通过我们定义的CBOW类，来构造一个CBOW模型网络
    CBOW_model = CBOW("CBOW_model", vocab_size, embedding_size)
    #构造训练这个网络的优化器
    adam = fluid.optimizer.AdamOptimizer(learning_rate=learning_rate)

    #使用build_batch函数，以mini-batch为单位，遍历训练数据，并训练网络
    for span_batch, target_words_batch, label_batch in build_batch(
        dataset, batch_size, epoch_num):
        #使用fluid.dygraph.to_variable函数，将一个numpy的tensor，转换为飞桨可计算的tensor
        # span_batch_var = fluid.dygraph.to_variable(span_batch)
        # target_words_batch_var = fluid.dygraph.to_variable(target_words_batch)
        # label_batch_var = fluid.dygraph.to_variable(label_batch)

        #将转换后的tensor送入飞桨中，进行一次前向计算，并得到计算结果
        pred, loss = CBOW_model(span_batch, target_words_batch, label_batch)

        #通过backward函数，让程序自动完成反向计算
        loss.backward()
        #通过minimize函数，让程序根据loss，完成一步对参数的优化更新
        adam.minimize(loss)
        #使用clear_gradients函数清空模型中的梯度，以便于下一个mini-batch进行更新
        CBOW_model.clear_gradients()

        #每经过100个mini-batch，打印一次当前的loss，看看loss是否在稳定下降
        step += 1
        if step % 100 == 0:
            print("step %d, loss %.3f" % (step, loss.numpy()[0]))

        #经过10000个mini-batch，打印一次模型对eval_words中的10个词计算的同义词
        #这里我们使用词和词之间的向量点积作为衡量相似度的方法
        #我们只打印了5个最相似的词
        if step % 10000 == 0:
            get_similar_tokens('one', 5, CBOW_model.embedding._w)
            get_similar_tokens('she', 5, CBOW_model.embedding._w)
            get_similar_tokens('chip', 5, CBOW_model.embedding._w)
            
            


# In[ ]:




