import sys, os
import tensorflow as tf

sys.path.append(os.path.realpath('../..'))

from book_code.data_utils import *
from book_code.logmanager import *

batch_size = 128
num_steps = 6001
learning_rate = 0.3
relu_layers = 1

log_location = '/tmp/simple_nn_log'

def reformat(data, image_size, num_of_classes):
    data.train_dataset = data.train_dataset.reshape((-1, image_size * image_size)).astype(np.float32)
    data.valid_dataset = data.valid_dataset.reshape((-1, image_size * image_size)).astype(np.float32)
    data.test_dataset = data.test_dataset.reshape((-1, image_size * image_size)).astype(np.float32)

    # Map 0 to [1.0, 0.0, 0.0 ...], 1 to [0.0, 1.0, 0.0 ...]
    data.train_labels = (np.arange(num_of_classes) == data.train_labels[:, None]).astype(np.float32)
    data.valid_labels = (np.arange(num_of_classes) == data.valid_labels[:, None]).astype(np.float32)
    data.test_labels = (np.arange(num_of_classes) == data.test_labels[:, None]).astype(np.float32)

    return data


def accuracy(predictions, labels):
    return (100.0 * np.sum(np.argmax(predictions, 1) == np.argmax(labels, 1))
            / predictions.shape[0])

def nn_model(data, weights, biases):

    with tf.name_scope('FC_layer_1') as scope:
        layer_fc1 = tf.nn.bias_add(tf.matmul(data, weights['fc1']), biases['fc1'], name=scope)
    relu_layer = tf.nn.relu(layer_fc1)
    for relu in range(2, relu_layers + 1):
        relu_layer = tf.nn.relu(relu_layer)
    with tf.name_scope('FC_layer_2') as scope:
        layer_fc2 = tf.nn.bias_add(tf.matmul(relu_layer, weights['fc2']), biases['fc2'], name=scope)
    return layer_fc2


not_mnist, image_size, num_of_classes = prepare_not_mnist_dataset()
not_mnist = reformat(not_mnist, image_size, num_of_classes)

print('Training set', not_mnist.train_dataset.shape, not_mnist.train_labels.shape)
print('Validation set', not_mnist.valid_dataset.shape, not_mnist.valid_labels.shape)
print('Test set', not_mnist.test_dataset.shape, not_mnist.test_labels.shape)

graph = tf.Graph()
with graph.as_default():
    # Input data. For the training data, we use a placeholder that will be fed
    # at run time with a training minibatch.
    tf_train_dataset = tf.placeholder(tf.float32,
                                      shape=(batch_size, image_size * image_size), name='TRAIN_DATASET')
    tf_train_labels = tf.placeholder(tf.float32, shape=(batch_size, num_of_classes), name='TRAIN_LABEL')
    tf_valid_dataset = tf.constant(not_mnist.valid_dataset, name='VALID_DATASET')
    tf_test_dataset = tf.constant(not_mnist.test_dataset, name='TEST_DATASET')

    # Variables.
    weights = {
        'fc1': tf.Variable(tf.truncated_normal([image_size * image_size, num_of_classes]), name='weights'),
        'fc2': tf.Variable(tf.truncated_normal([num_of_classes, num_of_classes]), name='weights')
    }
    biases = {
        'fc1': tf.Variable(tf.truncated_normal([num_of_classes], name='biases')),
        'fc2': tf.Variable(tf.truncated_normal([num_of_classes], name='biases'))
    }

    for weight_key in sorted(weights.keys()):
        _ = tf.histogram_summary(weight_key + '_weights', weights[weight_key])

    for bias_key in sorted(biases.keys()):
        _ = tf.histogram_summary(bias_key + '_biases', biases[bias_key])

    # Training computation.
    logits = nn_model(tf_train_dataset, weights, biases)
    loss = tf.reduce_mean(
        tf.nn.softmax_cross_entropy_with_logits(logits, tf_train_labels))

    _ = tf.scalar_summary('nn_loss', loss)

    # Optimizer.
    optimizer = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss)

    # Predictions for the training, validation, and test data.
    train_prediction = tf.nn.softmax(logits)
    valid_prediction = tf.nn.softmax(nn_model(tf_valid_dataset, weights, biases))
    test_prediction = tf.nn.softmax(nn_model(tf_test_dataset, weights, biases))

with tf.Session(graph=graph) as session:
    # saving graph
    merged = tf.merge_all_summaries()
    writer = tf.train.SummaryWriter(log_location, session.graph_def)

    tf.initialize_all_variables().run()
    print("Initialized")
    for step in range(num_steps):
        sys.stdout.write('Training on batch %d of %d\r' % (step + 1, num_steps))
        sys.stdout.flush()
        # Pick an offset within the training data, which has been randomized.
        # Note: we could use better randomization across epochs.
        offset = (step * batch_size) % (not_mnist.train_labels.shape[0] - batch_size)
        # Generate a minibatch.
        batch_data = not_mnist.train_dataset[offset:(offset + batch_size), :]
        batch_labels = not_mnist.train_labels[offset:(offset + batch_size), :]
        # Prepare a dictionary telling the session where to feed the minibatch.
        # The key of the dictionary is the placeholder node of the graph to be fed,
        # and the value is the numpy array to feed to it.
        feed_dict = {tf_train_dataset: batch_data, tf_train_labels: batch_labels}
        summary_result, _, l, predictions = session.run(
            [merged, optimizer, loss, train_prediction], feed_dict=feed_dict)

        writer.add_summary(summary_result, step)

        if (step % 500 == 0):
            logger.info('Step %03d  Acc Minibatch: %03.2f%%  Acc Val: %03.2f%%  Minibatch loss %f' % (
                step, accuracy(predictions, batch_labels), accuracy(
                valid_prediction.eval(), not_mnist.valid_labels), l))
    print("Test accuracy: %.1f%%" % accuracy(test_prediction.eval(), not_mnist.test_labels))