#!/bin/bash
set -o errexit
<<<<<<< HEAD

=======
export SETUPTOOLS_USE_DISTUTILS=stdlib
>>>>>>> rescue
USE_OFFICIAL_SOURCE=0
for arg in "$@"
do
    if [ "$arg" = "us" ]; then
        USE_OFFICIAL_SOURCE=1
    fi
done

<<<<<<< HEAD
rm -f ~/.condarc
conda create -n sandbox-runtime -y python=3.10

source activate sandbox-runtime
=======
# rm -f ~/.condarc
# conda create -n sandbox-runtime -y python=3.11
# conda activate sandbox-runtime
>>>>>>> rescue

if [ $USE_OFFICIAL_SOURCE -eq 0 ]; then
    pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
fi

<<<<<<< HEAD
pip install -r ./requirements.txt --ignore-requires-python
=======
pip install -r ./requirements.txt
>>>>>>> rescue

# for NaturalCodeBench python problem 29
python -c "import nltk; nltk.download('punkt')"

# for CIBench nltk problems 
python -c "import nltk; nltk.download('stopwords')"

pip cache purge
conda clean --all -y
