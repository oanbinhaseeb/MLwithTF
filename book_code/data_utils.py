import os, sys, tarfile
from six.moves.urllib.request import urlretrieve

import numpy as np
from scipy import ndimage

import pickle

MB = 1024 ** 2


def download_hook_function(block, block_size, total_size):
    if total_size != -1:
        sys.stdout.write('Downloaded: %3.3fMB of %3.3fMB\r' % (float(block * block_size) / float(MB),
                                                  float(total_size) / float(MB)))
    else:
        sys.stdout.write('Downloaded: %3.3fMB of \'unknown size\'\r' % (float(block * block_size) / float(MB)))

    sys.stdout.flush()


def download_file(file_url, output_file_dir, expected_size, FORCE=False):
    name = file_url.split('/')[-1]
    file_output_path = os.path.join(output_file_dir, name)
    print('Attempting to download ' + file_url)
    print('File output path: ' + file_output_path)
    print('Expected size: ' + str(expected_size))
    if not os.path.isdir(output_file_dir):
        os.makedirs(output_file_dir)

    if os.path.isfile(file_output_path) and os.stat(file_output_path).st_size == expected_size and not FORCE:
        print('File already downloaded completely!')
        return file_output_path
    else:
        print(' ')
        filename, _ = urlretrieve(file_url, file_output_path, download_hook_function)
        print(' ')
        statinfo = os.stat(filename)
        if statinfo.st_size == expected_size:
            print('Found and verified', filename)
        else:
            raise Exception('Could not download ' + filename)
        return filename


def extract_file(input_file, output_dir, FORCE=False):
    if os.path.isdir(output_dir) and not FORCE:
        print('%s already extracted to %s' % (input_file, output_dir))
        directories = [x for x in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, x))]
        return output_dir + "/" + directories[0]
    else:
        tar = tarfile.open(input_file)
        sys.stdout.flush()
        print('Started extracting %s to %s' % (input_file, output_dir))
        tar.extractall(output_dir)
        print('Finished extracting %s to %s' % (input_file, output_dir))
        tar.close()
        directories = [x for x in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, x))]
        return output_dir + "/" + directories[0]


def load_class(folder, image_size, pixel_depth):

    image_files = os.listdir(folder)
    num_of_images = len(image_files)
    dataset = np.ndarray(shape=(num_of_images, image_size, image_size),
                         dtype=np.float32)
    image_index = 0
    print('Started loading images from: ' + folder)
    for index, image in enumerate(image_files):

        sys.stdout.write('Loading image %d of %d\r' % (index + 1, num_of_images))
        sys.stdout.flush()

        image_file = os.path.join(folder, image)

        try:
            image_data = (ndimage.imread(image_file).astype(float) -
                          pixel_depth / 2) / pixel_depth
            if image_data.shape != (image_size, image_size):
                raise Exception('Unexpected image shape: %s' % str(image_data.shape))
            dataset[image_index, :, :] = image_data
            image_index += 1
        except IOError as e:
            print('Could not read:', image_file, ':', e, '- it\'s ok, skipping.')
    print('Finished loading data from: ' + folder)

    return dataset[0:image_index, :, :]


def make_pickles(input_folder, output_dir, image_size, image_depth, FORCE=False):
    directories = sorted([x for x in os.listdir(input_folder) if os.path.isdir(os.path.join(input_folder, x))])
    pickle_files = [os.path.join(output_dir, x + '.pickle') for x in directories]

    for index, pickle_file in enumerate(pickle_files):

        if os.path.isfile(pickle_file) and not FORCE:
            print('Pickle: %s already exsist' % (pickle_file))
        else:
            folder_path = os.path.join(input_folder, directories[index])
            print('Loading from folder: ' + folder_path)
            data = load_class(folder_path, image_size, image_depth)

            if not os.path.isdir(output_dir):
                os.makedirs(output_dir)

            print('Started pickling: ' + directories[index])
            try:
                with open(pickle_file, 'wb') as f:
                    pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)
            except Exception as e:
                print('Unable to save data to', pickle_file, ':', e)
            print('Finished pickling: ' + directories[index])

    return pickle_files

def randomize(dataset, labels):
    permutation = np.random.permutation(labels.shape[0])
    shuffled_dataset = dataset[permutation, :, :]
    shuffled_labels = labels[permutation]
    return shuffled_dataset, shuffled_labels


def make_arrays(nb_rows, img_size):
    if nb_rows:
        dataset = np.ndarray((nb_rows, img_size, img_size), dtype=np.float32)
        labels = np.ndarray(nb_rows, dtype=np.int32)
    else:
        dataset, labels = None, None
    return dataset, labels


def merge_datasets(pickle_files, image_size,train_size, valid_size=0):

    num_classes = len(pickle_files)
    valid_dataset, valid_labels = make_arrays(valid_size, image_size)
    train_dataset, train_labels = make_arrays(train_size, image_size)
    vsize_per_class = valid_size // num_classes
    tsize_per_class = train_size // num_classes

    start_v, start_t = 0, 0
    end_v, end_t = vsize_per_class, tsize_per_class
    end_l = vsize_per_class + tsize_per_class
    for label, pickle_file in enumerate(pickle_files):
        try:
            with open(pickle_file, 'rb') as f:
                letter_set = pickle.load(f)
                # let's shuffle the letters to have random validation and training set
                np.random.shuffle(letter_set)
                if valid_dataset is not None:
                    valid_letter = letter_set[:vsize_per_class, :, :]
                    valid_dataset[start_v:end_v, :, :] = valid_letter
                    valid_labels[start_v:end_v] = label
                    start_v += vsize_per_class
                    end_v += vsize_per_class

                train_letter = letter_set[vsize_per_class:end_l, :, :]
                train_dataset[start_t:end_t, :, :] = train_letter
                train_labels[start_t:end_t] = label
                start_t += tsize_per_class
                end_t += tsize_per_class
        except Exception as e:
            print('Unable to process data from', pickle_file, ':', e)
            raise

    return valid_dataset, valid_labels, train_dataset, train_labels


def pickle_whole(train_pickle_files, test_pickle_files, image_size,
                 train_size, valid_size, test_size, output_file_path, FORCE=False):
    if os.path.isfile(output_file_path) and not FORCE:
        print('Pickle file: %s already exist' % (output_file_path))

        with open(output_file_path, 'rb') as f:
            save = pickle.load(f)
            train_dataset = save['train_dataset']
            train_labels = save['train_labels']
            valid_dataset = save['valid_dataset']
            valid_labels = save['valid_labels']
            test_dataset = save['test_dataset']
            test_labels = save['test_labels']
            del save  # hint to help gc free up memory
            print('Training set', train_dataset.shape, train_labels.shape)
            print('Validation set', valid_dataset.shape, valid_labels.shape)
            print('Test set', test_dataset.shape, test_labels.shape)

        return train_dataset, train_labels, valid_dataset, valid_labels, test_dataset, test_labels
    else:
        print('Merging train, valid data')
        valid_dataset, valid_labels, train_dataset, train_labels = merge_datasets(
            train_pickle_files, image_size, train_size, valid_size)
        print('Merging test data')
        _, _, test_dataset, test_labels = merge_datasets(test_pickle_files, image_size, test_size)
        print('Training set', train_dataset.shape, train_labels.shape)
        print('Validation set', valid_dataset.shape, valid_labels.shape)
        print('Test set', test_dataset.shape, test_labels.shape)

        train_dataset, train_labels = randomize(train_dataset, train_labels)
        test_dataset, test_labels = randomize(test_dataset, test_labels)
        valid_dataset, valid_labels = randomize(valid_dataset, valid_labels)
        try:
            f = open(output_file_path, 'wb')
            save = {
                'train_dataset': train_dataset,
                'train_labels': train_labels,
                'valid_dataset': valid_dataset,
                'valid_labels': valid_labels,
                'test_dataset': test_dataset,
                'test_labels': test_labels,
            }
            pickle.dump(save, f, pickle.HIGHEST_PROTOCOL)
            f.close()
        except Exception as e:
            print('Unable to save data to', output_file_path, ':', e)
            raise

        statinfo = os.stat(output_file_path)
        print('Compressed pickle size:', statinfo.st_size)

        return train_dataset, train_labels, valid_dataset, valid_labels, test_dataset, test_labels


def prepare_not_mnist_dataset():
    print('Started preparing notMNIST dataset')

    image_size = 28
    image_depth = 255
    train_download_size = 247336696
    test_download_size = 8458043

    train_size = 200000
    valid_size = 10000
    test_size = 10000

    num_of_classes = 10

    train_file_path = download_file('http://yaroslavvb.com/upload/notMNIST/notMNIST_large.tar.gz',
                            os.path.realpath('../../datasets/notMNIST'), train_download_size)
    test_file_path = download_file('http://yaroslavvb.com/upload/notMNIST/notMNIST_small.tar.gz',
                            os.path.realpath('../../datasets/notMNIST'), test_download_size)

    train_extracted_folder = extract_file(train_file_path, os.path.realpath('../../datasets/notMNIST/train'))
    test_extracted_folder = extract_file(test_file_path, os.path.realpath('../../datasets/notMNIST/test'))

    print('Started loading training data')
    train_pickle_files = make_pickles(train_extracted_folder, os.path.realpath('../../datasets/notMNIST/train'),
                                      image_size, image_depth)
    print('Finished loading training data\n')

    print('Started loading testing data')
    test_pickle_files = make_pickles(test_extracted_folder, os.path.realpath('../../datasets/notMNIST/test'),
                                     image_size, image_depth)
    print('Finished loading testing data')

    print('Started pickling final dataset')
    train_dataset, train_labels, valid_dataset, valid_labels,\
        test_dataset, test_labels = pickle_whole(train_pickle_files, test_pickle_files, image_size, train_size, valid_size,
                                test_size, os.path.realpath('../../datasets/notMNIST/notMNIST.pickle'))
    print('Finished pickling final dataset')

    print('Finished preparing notMNIST dataset')

    def not_mnist(): pass

    not_mnist.train_dataset = train_dataset
    not_mnist.train_labels = train_labels
    not_mnist.valid_dataset = valid_dataset
    not_mnist.valid_labels = valid_labels
    not_mnist.test_dataset = test_dataset
    not_mnist.test_labels = test_labels

    return not_mnist, image_size, num_of_classes
