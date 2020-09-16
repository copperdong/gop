# import declaration
from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse
#from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, File, UploadFile
import uvicorn
from timing_asgi import TimingMiddleware, TimingClient
from timing_asgi.integrations import StarletteScopeToName
from fastapi.responses import JSONResponse
from  subprocess import Popen,PIPE
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import re

#initialization
app = FastAPI()

# Jinja2 template instance for returning webpage via template engine
#templates = Jinja2Templates(directory="templates")



# hello world, GET method, return string
@app.get("/", response_class=PlainTextResponse)
async def hello():
    return "Hello World!"

class PrintTimings(TimingClient):
    def timing(self, metric_name, timing, tags):
        print("time taken for :", tags[1],"request is:- ",timing )

@app.post("/gop/")
async def create_file(upload_file:UploadFile = File(...),email: str = Form(...),text:str=Form(...)):
    if upload_file.filename.endswith('.wav') or upload_file.filename.endswith('.mp3'):
        try:
            suffix = Path(upload_file.filename).suffix
            with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(upload_file.file, tmp)
                tmp_path = Path(tmp.name)
        finally:
            upload_file.file.close()
        try:
            process = Popen(('/home/ec2-user/ffmpeg','-y', '-i', tmp_path,'-ar' ,'16000', '/home/ec2-user/test/user_1.wav'))
            stdout, stderr = process.communicate()
            if stderr:
                print(stderr)
            with open('/home/ec2-user/models/data/test/text', 'w+') as f:
                l1 = "{}  {}".format("user_t1", str(text.upper()))
                f.write(l1)
            os.system('cp -r /home/ec2-user/models/data/test/ /home/ec2-user/models/data/eval2000')
            process2 = Popen(('/home/ec2-user/kaldi/kaldi/egs/gop/s5/gop_run.sh'), stdout=PIPE,stderr=PIPE, shell=True)
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
            for i in dp:
                z = i.split()
                if float(z[0]) > 2:  # removing silence phones
                    phone_gop_values.append(float(z[1]))
                    p_hones.append(pure_phone_dict.get(int(z[0])))

            max_old = max(phone_gop_values)
            min_old = min(phone_gop_values)
            total_score = 0
            gop_scores = {}
            count = 0
            for i in phone_gop_values:
                scaled_num = ((100 / (max_old - min_old)) * (i - min_old))
                #print("{:.2f}".format(scaled_num))
                gop_scores[str(p_hones[count])] = scaled_num
                total_score += scaled_num
                count = count + 1
            print("score is:- ", total_score // len(phone_gop_values))
            final_dict['overall_GoP_score'] = total_score // len(phone_gop_values)

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
            sep_scores={}
            phoneme_to_word=dict((v, k) for k, v in word_phones.items())
            for word_p in word_phones.values():
                scores = {}
                word_score=0
                sum_score=0
                p_s=""
                if str(word_p) != "NULL":
                    for j in p_hones:
                        if len(word_p) == len(p_s):
                            for i in scores.keys():
                                p_hones.remove(i)
                            break
                        else:
                            if j in word_p:
                                p_s=p_s+j
                                scores[j] = gop_scores.get(str(j))
                                sum_score=sum_score+gop_scores.get(str(j))
                    scores['word_score'] = (sum_score // (len(scores.keys())))
                    total_word_score=total_word_score+(sum_score // (len(scores.keys())))
                    if ''.join(list(scores.keys())[:-1]) == word_p:
                        sep_scores[phoneme_to_word[word_p]] = scores
                    else:
                        score={'word_score':0}
                        sep_scores[phoneme_to_word[word_p]] =score

            final_dict['total word score']=total_word_score//len(word_phones.values())
            final_dict['phone_scores'] = sep_scores
            # removing files for next run
            os.system('rm -r /home/ec2-user/output/gop.1.txt')
            return JSONResponse(content=final_dict)

        except Exception as er:
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
    uvicorn.run('app_v1:app', host='0.0.0.0', port=8080)
