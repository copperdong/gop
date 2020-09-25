# import declaration
from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse
#from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from timing_asgi import TimingMiddleware, TimingClient
from timing_asgi.integrations import StarletteScopeToName
from fastapi.responses import JSONResponse
import boto3
from botocore.exceptions import ClientError
from  subprocess import Popen,PIPE
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import re
from collections import defaultdict


#initialization
app = FastAPI()

# Jinja2 template instance for returning webpage via template engine
#templates = Jinja2Templates(directory="templates")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# hello world, GET method, return string
@app.get("/", response_class=PlainTextResponse)
async def hello():
    return "Hello World!"

class PrintTimings(TimingClient):
    def timing(self, metric_name, timing, tags):
        print("time taken for :", tags[1],"request is:- ",timing )

@app.post("/gop/")
async def get_gop(upload_file:UploadFile = File(...),email: str = Form(...),text:str=Form(...)):
    if upload_file.filename.endswith('.wav') or upload_file.filename.endswith('.mp3'):
        #saving temporary file
        try:
            suffix = Path(upload_file.filename).suffix
            with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(upload_file.file, tmp)
                tmp_path = Path(tmp.name)
        finally:
            upload_file.file.close()

        #saving file to aws 
        try:
            # YOUR AWS IAM ACCESS KEY AND SECRET, GET IT FROM THE IAM CONSOLE
            s3_client = boto3.client('s3', aws_access_key_id='*****************', aws_secret_access_key='*************************')
            filename=email.split('@')[0].replace('.', '_') + '_sep_' + upload_file.filename
            file_name='/home/ec2-user/test/'+filename[:-3]+'wav'

            # storing into BUCKET
            response=s3_client.upload_file(str(tmp_path),'bucket_name','incoming/test/'+filename)
            #storing text file

            text_dta ="{}'{}'".format("b",str(text.upper()))
            response1=s3_client.put_object(Body=text_dta, Bucket='bucket_name', Key='incoming/test/'+filename[:-3]+'txt')

        except ClientError as e:
                print("S3 file uploading error",e)
        try:
            process = Popen(('/home/ec2-user/ffmpeg','-y', '-i', tmp_path,'-ar','16000',file_name))
            stdout, stderr = process.communicate()
            if stderr:
                print(stderr)
            with open('/home/ec2-user/models/data/test/text', 'w+') as f:
                text=re.sub('\W+',' ', text)
                l1 = "{}  {}".format("user_t1", str(text.upper()))
                f.write(l1)
            with open('/home/ec2-user/models/data/test/wav.scp', 'w+') as f:
                l1 = "{}  {}".format("user_t1",file_name)
                f.write(l1)

            os.system('cp -r /home/ec2-user/models/data/test/ /home/ec2-user/models/data/eval2000')
            process2 = Popen(('/home/ec2-user/kaldi/kaldi/egs/gop/s5/gop_run.sh',file_name), stdout=PIPE,stderr=PIPE, shell=True)
            stdout, stderr = process2.communicate()
            if stderr:
                print(stderr)
            else:
                print(stdout)
                # raise Exception("Error " + str(stderr))

            # computing GoP score from GoP output files
            # final dictionary
            final_dict = {}
            # creating a dictionary with pure-phone id and it's corressponding phone (sil-> 3)
            with open('/home/ec2-user/reqd_files/phones-pure.txt') as pp:
                pure_phones = pp.read()
            pure_phone_dict = {}
            pp_rows = pure_phones.split('\n')
            for pp in pp_rows:
                if pp:
                    pure_phone_dict[int(pp.split('\t')[1])] = str(pp.split('\t')[0])
                # getting GoP data
            with open('/home/ec2-user/output/gop.1.txt') as g:
                gop_data = g.read()

            lines = gop_data.split("\n")
            dp = re.findall(r'\[(.*?)\]', lines[0])
            # storing phones and it's values to separate lists
            phone_gop_values = []
            p_hones = []
            num_silence=0
            for i in dp:
                z = i.split()
                if float(z[0]) > 2:  # removing silence phones
                    phone_gop_values.append(float(z[1]))
                    p_hones.append(pure_phone_dict.get(int(z[0])))
                else:
                    num_silence=num_silence+1
            max_old = max(phone_gop_values)
            min_old = min(phone_gop_values)
            total_score = 0
            gop_scores=defaultdict(list)
            count=0
            for i in phone_gop_values:
                scaled_num=((100/(max_old-min_old)) * (i-min_old))
                #print("{:.2f}".format(scaled_num))
                gop_scores[str(p_hones[count])].append(scaled_num)
                total_score+=scaled_num
                count=count+1
            print("score is:- ",total_score//len(phone_gop_values))
            final_dict['overall_GoP_score']=total_score//len(phone_gop_values)
            final_dict['no_of_silences']=num_silence
            final_dict['no_of_phones']=len(p_hones)
            final_dict['gop_phoneme_scores']=gop_scores
            # getting Phonemes of actual transcripts
            # storing words and corresponding phoneme representation to dictionary
            with open('/home/ec2-user/reqd_files/align_lexicon.txt') as f:
                data = f.read()
            all_rows = data.split('\n')
            phones_dict = {}
            for row in all_rows:
                if row:
                    c_phoneme = ""
                    for i in row.split()[1:][1:]:
                        c_phoneme += str(i)
                    phones_dict[str(row.split()[1:][0])] = c_phoneme
            # getting words in the transcripts and corresponding phoneme
            text_words = text.split()

            # converting phones to pure phones by removing markers(start,end, inter,s) and also numbers
            word_phones = {}
            for word in text_words:
                if (phones_dict.get(str(word).upper())):
                    phoneme = phones_dict.get(str(word).upper())
                    phoneme = ''.join([i for i in phoneme if not i.isdigit()])
                    phoneme = re.sub('_.{1}', '', phoneme)
                    word_phones[str(word)] = phoneme
                else:
                    word_phones[str(word)] = 'NULL'
            total_word_score=0
            sep_scores=defaultdict(list)
            phoneme_to_word=dict((v, k) for k, v in word_phones.items())
            occured_phones=[]
            p_hones_copy=p_hones[:]
            for word_p in word_phones.values():
                scores = defaultdict(list)
                word_score=0
                sum_score=0
                p_s=""
                if str(word_p) != "NULL":
                    for j in p_hones:
                        if len(word_p) == len(p_s):
                            for i in scores.keys():
                                for j in range(len(scores[i])):
                                    p_hones.remove(i)
                            break
                        else:
                             if j in word_p:
                                 p_s=p_s+j
                                 if j in occured_phones:
                                     scores[j].append(gop_scores.get(str(j))[-1])
                                     del gop_scores.get(str(j))[-1]
                                 else:
                                     scores[j].append(gop_scores.get(str(j))[-1])
                                 sum_score=sum_score+gop_scores.get(str(j))[-1]

                    #print(sum([len(vals) for k, vals in scores.items()]))
                    sns=[]
                    for k, vals in scores.items():
                        for i in range(len(vals)):
                            sns.append(k)
                    #total_word_score = total_word_score + (sum_score // (len(sns)))

                    if len(''.join(sns)) == len(word_p):
                        scores['word_score'] = (sum_score // (len(sns)))
                        sep_scores[str(word_p)].append(dict(scores))
                        total_word_score = total_word_score + (sum_score // (len(sns)))
                    else:
                        score={'word_score':0}
                        sep_scores[str(word_p)].append(dict(score))
                        total_word_score = total_word_score + 0

            final_dict['total word score']=total_word_score//len(word_phones.values())
            final_dict['phone_scores'] = dict(sep_scores)

            print(final_dict)
            #storing in output directory on s3
            response=s3_client.upload_file('/home/ec2-user/output/gop.1.txt','bucket_name','outgoing/test/'+filename[:-3]+'gop.txt')
            # removing files for next run
            os.system('rm -r /home/ec2-user/output/gop.1.txt')
            return JSONResponse(content=final_dict)

        except Exception as er:
            if str(er)=="integer division or modulo by zero":
                return "Unable to decode the audio"
            if str(er)=="max() arg is an empty sequence":
                return "Unable to decode the audio (oov words)"
            print(er)
            return "error occured while  calculating GoP"

    else:
        return "Please Upload either .mp3 or .wav file "

app.add_middleware(
    TimingMiddleware,
    client=PrintTimings(),
    metric_namer=StarletteScopeToName(prefix="myapp", starlette_app=app)
)

# main
if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8080)
