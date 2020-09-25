set -e
# Global configurations
stage=1
nj=1  #set nj=2 for splitting (nj= Number of speakers)
cmd=run.pl


. /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/cmd.sh
. /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/path.sh
. /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/utils/parse_options.sh

data=/home/ec2-user/models/data/test_clean_hires
dir=/home/ec2-user/models/exp/nnet3_cleaned/aligns
# Before running this recipe, you have to run the librispeech recipe firstly.
# This script assumes the following paths exist.
librispeech_eg=/home/ec2-user/models
model=$librispeech_eg/exp/nnet3_cleaned/tdnn_sp
ivector=$librispeech_eg/exp/nnet3_cleaned/ivectors_test_clean_hires
lang=$librispeech_eg/data/lang
test_data=$librispeech_eg/data/test_clean_hires



# Creating MFCC and ivectors
if [ $stage -le 1 ]; then
  # Extracting mfcc features and ivectors of the  test data
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/utils/fix_data_dir.sh '/home/ec2-user/models/data/eval2000/'
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/utils/copy_data_dir.sh '/home/ec2-user/models/data/eval2000/' '/home/ec2-user/models/data/test_clean_hires'
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/utils/fix_data_dir.sh '/home/ec2-user/models/data/test_clean_hires'
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/steps/make_mfcc.sh --mfcc-config /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/conf/mfcc_hires.conf --nj $nj '/home/ec2-user/models/data/test_clean_hires'
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/steps/compute_cmvn_stats.sh '/home/ec2-user/models/data/test_clean_hires'
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/utils/fix_data_dir.sh '/home/ec2-user/models/data/test_clean_hires'
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/steps/online/nnet2/extract_ivectors.sh --nj $nj --cmd "$cmd" '/home/ec2-user/models/data/test_clean_hires' '/home/ec2-user/models/data/lang' '/home/ec2-user/models/exp/nnet3_cleaned/extractor' '/home/ec2-user/models/exp/nnet3_cleaned/ivectors_test_clean_hires'
fi


for d in $model $ivector $lang $test_data; do
  [ ! -d $d ] && echo "$0: no such path $d" && exit 1;
done


if [ $stage -le 2 ]; then
   # Compute Log-likelihoods
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/steps/nnet3/compute_output.sh --cmd "$cmd" --nj $nj \
    --online-ivector-dir $ivector $data $model /home/ec2-user/models/exp/probs_test_clean_hires
fi

if [ $stage -le 3 ]; then
  /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/steps/nnet3/align.sh --cmd "$cmd" --nj $nj --use_gpu false \
    --online_ivector_dir $ivector $data $lang $model $dir

fi

if [ $stage -le 4 ]; then
  # make a map which converts phones to "pure-phones"
  # "pure-phone" means the phone whose stress and pos-in-word markers are ignored
  # eg. AE1_B --> AE, EH2_S --> EH, SIL --> SIL
  /home/ec2-user/kaldi/kaldi/egs/gop/s5/local/remove_phone_markers.pl $lang/phones.txt $dir/phones-pure.txt \
    $dir/phone-to-pure-phone.int

  # Convert transition-id to pure-phone id
  $cmd JOB=1:$nj $dir/log/ali_to_phones.JOB.log \
    /home/ec2-user/kaldi/kaldi/src/bin/ali-to-phones --per-frame=true $model/final.mdl "ark,t:gunzip -c $dir/ali.JOB.gz|" \
      "ark,t:-" \| /home/ec2-user/kaldi/kaldi/egs/librispeech/s5/utils/apply_map.pl -f 2- $dir/phone-to-pure-phone.int \| \
      gzip -c \>$dir/ali-pure-phone.JOB.gz   || exit 1;
fi
if [ $stage -le 5 ]; then
  # The outputs of the binary compute-gop are the GOPs and the phone-level features.
  #
  # An example of the GOP result (extracted from "ark,t:$dir/gop.3.txt"):
  # 4446-2273-0031 [ 1 0 ] [ 12 0 ] [ 27 -5.382001 ] [ 40 -13.91807 ] [ 1 -0.2555897 ] \
  #                [ 21 -0.2897284 ] [ 5 0 ] [ 31 0 ] [ 33 0 ] [ 3 -11.43557 ] [ 25 0 ] \
  #                [ 16 0 ] [ 30 -0.03224623 ] [ 5 0 ] [ 25 0 ] [ 33 0 ] [ 1 0 ]
  # It is in the posterior format, where each pair stands for [pure-phone-index gop-value].
  # For example, [ 27 -5.382001 ] means the GOP of the pure-phone 27 (it corresponds to the
  # phone "OW", according to "$dir/phones-pure.txt") is -5.382001, indicating the audio
  # segment of this phone should be a mispronunciation.
  #
  # The phone-level features are in matrix format:
  # 4446-2273-0031  [ -0.2462088 -10.20292 -11.35369 ...
  #                   -8.584108 -7.629755 -13.04877 ...
  #                   ...
  #                   ... ]
  # The row number is the phone number of the utterance. In this case, it is 17.
  # The column number is 2 * (pure-phone set size), as the feature is consist of LLR + LPR.
  # The phone-level features can be used to train a classifier with human labels. See Hu's
  # paper for detail.
  $cmd JOB=1:$nj $dir/log/compute_gop.JOB.log \
    /home/ec2-user/kaldi/kaldi/src/bin/compute-gop --phone-map=$dir/phone-to-pure-phone.int $model/final.mdl \
      "ark,t:gunzip -c $dir/ali-pure-phone.JOB.gz|" \
      "ark:/home/ec2-user/models/exp/probs_test_clean_hires/output.JOB.ark" \
      "ark,t:/home/ec2-user/output/gop.JOB.txt" "ark,t:$dir/phonefeat.JOB.txt"   || exit 1;
  echo "Done compute-gop, the results: \"/home/ec2-user/output/gop.<JOB>.txt\" in posterior format."

  # We set -5 as a universal empirical threshold here. You can also determine multiple phone
  # dependent thresholds based on the human-labeled mispronunciation data.
  #echo "The phones whose gop values less than -5 could be treated as mispronunciations
fi

  rm -r /home/ec2-user/models/data/eval2000 /home/ec2-user/models/data/test_clean_hires /home/ec2-user/models/exp/nnet3_cleaned/ivectors_test_clean_hires  /home/ec2-user/models/exp/probs_test_clean_hires  /home/ec2-user/models/exp/nnet3_cleaned/aligns $1
