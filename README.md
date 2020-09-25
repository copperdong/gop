# gop
Compute Goodness of Pronunciation using Kaldi

<h4> Installation </h4>

<ol>
  <li>Move these files to kaldi/egs/gop
</li>
  <li>change the file paths in gop_run.sh and and main.py 
</li>
  <li>install pip 
</li>
  </li>
  <li> install requirements for fastapi using
`pip install -r requirements.txt`
</li>
</li>
  <li>run the app using uvicorn 
  `gunicorn -w 2 --reload --bind 0.0.0.0:8080 --capture-output --error-logfile error_log.txt --access-logfile log.txt -k uvicorn.workers.UvicornWorker main:app`
</li>
 <li>open localhost:8080/docs to check the docs
</li>
</ol>








