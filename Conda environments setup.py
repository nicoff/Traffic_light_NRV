

in the folder of the project:
conda create --name TL_alarm python=3.11
conda activate TL_alarm
conda install requests urllib3
 CTRL Shift P
 select interpreter --> miniconda3\envs\TL_alarm\python.exe
conda env export > environment.yml
conda list --export > requirements.txt
conda deactivate
...
conda activate TL_alarm