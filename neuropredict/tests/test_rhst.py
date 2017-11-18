
import numpy as np
import os
import sys
from sys import version_info
import shlex
from os.path import join as pjoin, exists as pexists, realpath, dirname, abspath

sys.dont_write_bytecode = True

from pyradigm import MLDataset
import pytest
from pytest import raises, warns

if __name__ == '__main__' and __package__ is None:
    parent_dir = dirname(dirname(abspath(__file__)))
    sys.path.append(parent_dir)

if version_info.major==2 and version_info.minor==7:
    from neuropredict import rhst, run_workflow
elif version_info.major > 2:
    from neuropredict import rhst, run_workflow, cli
else:
    raise NotImplementedError('neuropredict supports only 2.7 or Python 3+. Upgrade to Python 3+ is recommended.')

feat_generator = np.random.randn

out_dir = os.path.abspath('../tests')
if not pexists(out_dir):
    os.makedirs(out_dir)

meta_file = os.path.join(out_dir,'meta.csv')

meta = list()

def make_random_MLdataset(max_num_classes = 20,
                          max_class_size = 50,
                          max_dim = 100,
                          stratified = True):
    "Generates a random MLDataset for use in testing."

    num_classes = np.random.randint(2, max_num_classes, 1)
    if type(num_classes) == np.ndarray:
        num_classes = num_classes[0]
    if not stratified:
        class_sizes = np.random.random_integers(min(50, max_class_size),
                                                max(50, max_class_size),
                                                size=[num_classes, 1])
    else:
        class_sizes = np.repeat(np.random.randint(min(50, max_class_size),
                                                  max(50, max_class_size)),
                                                  num_classes)

    num_features = np.random.randint(min(3, max_dim), max(3, max_dim), 1)[0]
    feat_names = [ str(x) for x in range(num_features)]

    class_ids = list()
    labels = list()
    for cl in range(num_classes):
        class_ids.append('class-{}'.format(cl))
        labels.append(int(cl))

    ds = MLDataset()
    for cc, class_ in enumerate(class_ids):
        subids = [ 'sub{:03}-class{:03}'.format(ix,cc) for ix in range(class_sizes[cc]) ]
        for sid in subids:
            ds.add_sample(sid, feat_generator(num_features), int(cc), class_, feat_names)

    return ds


max_num_classes = 3
max_class_size = 40
max_dim = 50
num_repetitions =  20

train_perc = 0.8
red_dim = 'sqrt'
classifier = 'extratreesclassifier'
gs_level = 'none'

num_procs = 1


# using a really small sample size for faster testing.
rand_ds = make_random_MLdataset(max_num_classes=max_num_classes, stratified=True,
    max_class_size = max_class_size, max_dim = max_dim)

out_path = os.path.join(out_dir, 'two_classes_random_features.pkl')
rand_two_class = rand_ds.get_class(rand_ds.class_set[0:3])
rand_two_class.save(out_path)

rand_ds2 = rand_ds # make_random_MLdataset(max_num_classes=max_num_classes, stratified=True, max_class_size = max_class_size, max_dim = max_dim)
out_path2 = os.path.join(out_dir, 'two_classes_random_features_another.pkl')
rand_ds2.save(out_path2)

ds_path_list = os.path.join(out_dir, 'same_data_two_classes_list_datasets.txt')
with open(ds_path_list, 'w') as lf:
    lf.writelines('\n'.join([out_path, out_path2]))

method_names = ['random1', 'another']

def test_chance_clf_binary_rfc():

    global ds_path_list, method_names, out_dir, num_repetitions, gs_level, train_perc, num_procs

    res_path = rhst.run(ds_path_list, method_names, out_dir,
                        train_perc=train_perc, num_repetitions=num_repetitions,
                        num_procs=num_procs, grid_search_level=gs_level)

    dataset_paths, method_names, train_perc, num_repetitions, num_classes, \
        pred_prob_per_class, pred_labels_per_rep_fs, test_labels_per_rep, \
        best_params, feature_importances_rf, feature_names, \
        num_times_misclfd, num_times_tested, \
        confusion_matrix, class_set, class_sizes, \
        accuracy_balanced, auc_weighted, positive_class, \
        classifier_name, feat_select_method= rhst.load_results(res_path)

    median_bal_acc = np.median(accuracy_balanced)
    # median_wtd_auc = np.median(auc_weighted)
    chance_acc = rhst.chance_accuracy(class_sizes)

    if abs(median_bal_acc-chance_acc) > chance_acc:
        raise ValueError('Chance accuracy estimated via repeated holdout CV to substantially differs from that based on class sizes : {}'.format(chance_acc))


def test_chance_clf_binary_etc():

    global ds_path_list, method_names, out_dir, num_repetitions, gs_level, train_perc, num_procs

    res_path = rhst.run(ds_path_list, method_names, out_dir,
                        train_perc=train_perc, num_repetitions=num_repetitions,
                        num_procs=num_procs, grid_search_level=gs_level,
                        classifier='extratreesclassifier')

    dataset_paths, method_names, train_perc, num_repetitions, num_classes, \
        pred_prob_per_class, pred_labels_per_rep_fs, test_labels_per_rep, \
        best_params, feature_importances_rf, feature_names, \
        num_times_misclfd, num_times_tested, \
        confusion_matrix, class_set, class_sizes, \
        accuracy_balanced, auc_weighted, positive_class, \
        classifier_name, feat_select_method= rhst.load_results(res_path)

    median_bal_acc = np.median(accuracy_balanced)
    # median_wtd_auc = np.median(auc_weighted)
    chance_acc = rhst.chance_accuracy(class_sizes)

    if abs(median_bal_acc-chance_acc) > chance_acc:
        raise ValueError('Chance accuracy estimated via repeated holdout CV to substantially differs from that based on class sizes : {}'.format(chance_acc))


def test_versioning():
    " ensures the CLI works. "

    with raises(SystemExit):
        sys.argv = shlex.split('neuropredict -v')
        cli()

def test_vis():
    " ensures the CLI works. "

    res_path = pjoin(out_dir, 'rhst_results.pkl')
    if pexists(res_path):
        with raises(SystemExit):
            sys.argv = shlex.split('neuropredict --make_vis {}'.format(out_dir))
            cli()
            expected_results = ['balanced_accuracy.pdf', 'compare_misclf_rates.pdf', 'feature_importance.pdf']
            for rpath in expected_results:
                if not pexists(rpath):
                    raise ValueError('an expected result {} not produced'.format(rpath))
    else:
        print('previously computed results not found in \n {}'.format(out_dir))

def test_arff():

    arff_path = realpath(pjoin(dirname(dirname(dirname(__file__))), # 3 levels up
                               'example_datasets', 'arff', 'iris.arff'))
    sys.argv = shlex.split('neuropredict -a {}'.format(arff_path))
    cli()


# res_path = pjoin(out_dir, 'rhst_results.pkl')
# run_workflow.make_visualizations(res_path, out_dir)
# test_chance_clf_binary_rfc()
# test_chance_clf_binary_etc()

# test_versioning()
# test_vis()

# etc_debug()

# test_arff()