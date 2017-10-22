import os
import sys
import numpy as np

import tensorflow as tf

from tensorflow.python.framework import ops
from tensorflow.python.ops import clip_ops

from bn_class import *

if sys.version_info[0] >= 3:
    from urllib.request import urlretrieve, ContentTooShortError
else:
    from urllib import urlretrieve, ContentTooShortError

dataset = "WIKI"
dataset_codes = ["ACN", "AIG", "GSIT"]
base_url = "https://www.quandl.com/api/v3/datasets/{}/{}/data.csv"

output_path = os.path.realpath('../../datasets/TimeSeries')

if not os.path.isdir(os.path.realpath('../../datasets/TimeSeries')):
    os.makedirs(output_path)


def make_url(ticker_symbol):
    return base_url.format(dataset, ticker_symbol)


def make_filename(ticker_symbol):
    return output_path + '/' + ticker_symbol + ".csv"


def pull_historical_data(ticker_symbol):
    try:
        urlretrieve(make_url(ticker_symbol), make_filename(ticker_symbol))
    except ContentTooShortError as e:
        outfile = open(make_filename(ticker_symbol), "w")
        outfile.write(e.content)
        outfile.close()


for aStock in dataset_codes:
    pull_historical_data(aStock)

closeData = {}
for aStock in dataset_codes:
    f = open(output_path + "/" + aStock + ".csv", 'r+')
    contents = f.read()
    print(contents)
    closeData[aStock] = contents.splitlines()

firstAvailDate = {}
for key, value in closeData.items():
    firstAvailDate[key] = value[-1].split(",")[0]
    print(key, firstAvailDate[key])

num_filt_1 = 12  # Number of filters in first conv layer
num_filt_2 = 8  # Number of filters in second conv layer
num_filt_3 = 8  # Number of filters in third conv layer
num_fc_1 = 40  # Number of neurons in fully connected layer

max_iterations = 2000
batch_size = 100
dropout = 0.5  # Dropout rate in the fully connected layer
regularization = 1e-4
learning_rate = 2e-3
input_norm = True

data_train = np.loadtxt('data_train_dummy', delimiter=',')
data_test_val = np.loadtxt('data_test_dummy', delimiter=',')
data_test, data_val = np.split(data_test_val, 2)

# Usually, the first column contains the target labels

X_train = data_train[:, 1:]
X_val = data_val[:, 1:]
X_test = data_test[:, 1:]
N = X_train.shape[0]
Ntest = X_test.shape[0]
D = X_train.shape[1]
y_train = data_train[:, 0]
y_val = data_val[:, 0]
y_test = data_test[:, 0]
print('We have %s observations with %s dimensions' % (N, D))

# Organize the classes
num_classes = len(np.unique(y_train))
base = np.min(y_train)  # Check if data is 0-based

if base != 0:
    y_train -= base
    y_val -= base
    y_test -= base

if input_norm:
    mean = np.mean(X_train, axis=0)
    variance = np.var(X_train, axis=0)
    X_train -= mean

    # The 1e-9 avoids dividing by zero

    X_train /= np.sqrt(variance) + 1e-9
    X_val -= mean
    X_val /= np.sqrt(variance) + 1e-9
    X_test -= mean
    X_test /= np.sqrt(variance) + 1e-9

# Proclaim the epochs
epochs = np.floor(batch_size * max_iterations / N)
print('Train with approximately %d epochs' % (epochs))

# Nodes for the input variables
x = tf.placeholder("float", shape=[None, D], name='Input_data')
y_ = tf.placeholder(tf.int64, shape=[None], name='Ground_truth')

keep_prob = tf.placeholder("float")
bn_train = tf.placeholder(tf.bool)


def weight_variable(shape, name):
    return tf.Variable(tf.truncated_normal(shape, stddev=0.1), name=name)


def bias_variable(shape, name):
    return tf.Variable(tf.constant(0.1, shape=shape), name=name)


def conv2d(x, W):
    return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='SAME')


def max_pool_2x2(x):
    return tf.nn.max_pool(x, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')


with tf.name_scope("Reshaping_data"):
    x_image = tf.reshape(x, [-1, D, 1, 1])

# ewma is the decay for which we update the moving average of the
# mean and variance in the batch-norm layers

with tf.name_scope("Conv1"):
    W_conv1 = weight_variable([5, 1, 1, num_filt_1], 'Conv_Layer_1')
    b_conv1 = bias_variable([num_filt_1], 'bias_for_Conv_Layer_1')
    a_conv1 = conv2d(x_image, W_conv1) + b_conv1

with tf.name_scope('Batch_norm_conv1'):
    ewma = tf.train.ExponentialMovingAverage(decay=0.99)
    bn_conv1 = ConvolutionalBatchNormalizer(num_filt_1, 0.001, ewma, True)

    update_assignments = bn_conv1.get_assigner()
    a_conv1 = bn_conv1.normalize(a_conv1, train=bn_train)
    h_conv1 = tf.nn.relu(a_conv1)

with tf.name_scope("Conv2"):
    W_conv2 = weight_variable([4, 1, num_filt_1, num_filt_2], 'Conv_Layer_2')
    b_conv2 = bias_variable([num_filt_2], 'bias_for_Conv_Layer_2')
    a_conv2 = conv2d(h_conv1, W_conv2) + b_conv2

with tf.name_scope('Batch_norm_conv2'):
    bn_conv2 = ConvolutionalBatchNormalizer(num_filt_2, 0.001, ewma, True)
    update_assignments = bn_conv2.get_assigner()
    a_conv2 = bn_conv2.normalize(a_conv2, train=bn_train)
    h_conv2 = tf.nn.relu(a_conv2)

with tf.name_scope("Conv3"):
    W_conv3 = weight_variable([4, 1, num_filt_2, num_filt_3], 'Conv_Layer_3')
    b_conv3 = bias_variable([num_filt_3], 'bias_for_Conv_Layer_3')
    a_conv3 = conv2d(h_conv2, W_conv3) + b_conv3

with tf.name_scope('Batch_norm_conv3'):
    bn_conv3 = ConvolutionalBatchNormalizer(num_filt_3, 0.001, ewma, True)

    update_assignments = bn_conv3.get_assigner()
    a_conv3 = bn_conv3.normalize(a_conv3, train=bn_train)

    h_conv3 = tf.nn.relu(a_conv3)

with tf.name_scope("Fully_Connected1"):
    W_fc1 = weight_variable([D * num_filt_3, num_fc_1], 'Fully_Connected_layer_1')
    b_fc1 = bias_variable([num_fc_1], 'bias_for_Fully_Connected_Layer_1')
    h_conv3_flat = tf.reshape(h_conv3, [-1, D * num_filt_3])
    h_fc1 = tf.nn.relu(tf.matmul(h_conv3_flat, W_fc1) + b_fc1)

with tf.name_scope("Fully_Connected2"):
    h_fc1_drop = tf.nn.dropout(h_fc1, keep_prob)

    W_fc2 = tf.Variable(tf.truncated_normal([num_fc_1, num_classes], stddev=0.1), name='W_fc2')
    b_fc2 = tf.Variable(tf.constant(0.1, shape=[num_classes]), name='b_fc2')
    h_fc2 = tf.matmul(h_fc1_drop, W_fc2) + b_fc2

with tf.name_scope("SoftMax"):
    regularizers = (tf.nn.l2_loss(W_conv1) + tf.nn.l2_loss(b_conv1) +
                    tf.nn.l2_loss(W_conv2) + tf.nn.l2_loss(b_conv2) +
                    tf.nn.l2_loss(W_conv3) + tf.nn.l2_loss(b_conv3) +
                    tf.nn.l2_loss(W_fc1) + tf.nn.l2_loss(b_fc1) +
                    tf.nn.l2_loss(W_fc2) + tf.nn.l2_loss(b_fc2))

    loss = tf.nn.sparse_softmax_cross_entropy_with_logits(h_fc2, y_)
    cost = tf.reduce_sum(loss) / batch_size
    cost += regularization * regularizers
    loss_summ = tf.summary.scalar("cross entropy_loss", cost)

with tf.name_scope("train"):
    tvars = tf.trainable_variables()

    # We clip the gradients to prevent explosion

    grads = tf.gradients(cost, tvars)
    optimizer = tf.train.AdamOptimizer(learning_rate)
    gradients = zip(grads, tvars)
    train_step = optimizer.apply_gradients(gradients)

    # The following block plots for every trainable variable

    # - Histogram of the entries of the Tensor

    # - Histogram of the gradient over the Tensor

    # - Histogram of the grradient-norm over the Tensor

    numel = tf.constant([[0]])
    for gradient, variable in gradients:
        if isinstance(gradient, ops.IndexedSlices):
            grad_values = gradient.values
        else:
            grad_values = gradient

        numel += tf.reduce_sum(tf.size(variable))

        h1 = tf.summary.histogram(variable.name, variable)
        h2 = tf.summary.histogram(variable.name + "/gradients", grad_values)
        h3 = tf.summary.histogram(variable.name + "/gradient_norm", clip_ops.global_norm([grad_values]))

with tf.name_scope("Evaluating_accuracy") as scope:
    correct_prediction = tf.equal(tf.argmax(h_fc2, 1), y_)

    accuracy = tf.reduce_mean(tf.cast(correct_prediction, "float"))
    accuracy_summary = tf.summary.scalar("accuracy", accuracy)

    # Define one op to call all summaries
    merged = tf.summary.merge_all()

perf_collect = np.zeros((3, int(np.floor(max_iterations / 100))))

with tf.Session() as sess:
    writer = tf.summary.FileWriter("/home/rob/Dropbox/ml_projects/CNN_tsc/log_tb", sess.graph_def)
    sess.run(tf.initialize_all_variables())

    step = 0  # Step is a counter for filling the numpy array perf_collect
    for i in range(max_iterations):
        batch_ind = np.random.choice(N, batch_size, replace=False)

        if i == 0:
            # Use this line to check before-and-after test accuracy

            result = sess.run(accuracy, feed_dict={x: X_test, y_: y_test, keep_prob: 1.0, bn_train: False})
            acc_test_before = result
        if i % 100 == 0:
            # Check training performance

            result = sess.run(accuracy, feed_dict={x: X_train, y_: y_train, keep_prob: 1.0, bn_train: False})
            perf_collect[1, step] = result

            # Check validation performance

            result = sess.run([accuracy, merged], feed_dict={x: X_val, y_: y_val, keep_prob: 1.0, bn_train: False})
            acc = result[0]
            perf_collect[0, step] = acc

            # Write information to TensorBoard

            summary_str = result[1]
            writer.add_summary(summary_str, i)
            writer.flush()  # Don't forget this command! It makes sure Python writes the summaries to the log-file

            print(" Validation accuracy at %s out of %s is %s" % (i, max_iterations, acc))

        step += 1

        sess.run(train_step, feed_dict={x: X_train[batch_ind], y_: y_train[batch_ind], keep_prob: dropout,
                                        bn_train: True})

        result = sess.run([accuracy, numel], feed_dict={x: X_test, y_: y_test, keep_prob: 1.0, bn_train: False})

        acc_test = result[0]

        print('The network has %s trainable parameters' % (result[1]))
