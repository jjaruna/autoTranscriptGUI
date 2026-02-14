import os
import sys
from langdetect import detect  # pip install langdetect
import regex as re  # Install with: pip install -U regex
import pickle
import openai  # Install with: pip install -U openai
import dotenv  # Install with pip install -U python-dotenv
import tqdm    # Install with: pip install -U tqdm

# Load environment variables
dotenv.load_dotenv()

# Define app parameters
MODEL = os.getenv("OPENAI_MODEL")
HOST = os.getenv("OPENAI_HOST", "")
PORT = os.getenv("OPENAI_PORT", 80)
API_KEY = os.getenv("OPENAI_API_KEY", "MY-KEY")
API_URL = f"http://{HOST}:{PORT}/v1"

# Function: Run user input against LLM
def process_llm(user_input:str, conversation_history:list=[], model:str=MODEL, temperature:float=0.5, DEBUG:bool=False) -> str:
    # Append current user input to conversation history
    conversation_history.append({"role": "user", "content": user_input})

    # Setup OpenAI-compatible client
    if HOST == "":
        client = openai.OpenAI(api_key=API_KEY)  # Use OpenAI
    else:
        client = openai.OpenAI(base_url=API_URL)  # Use custom OpenAI-compatible endpoint

    # Generate chat response from LLM
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=conversation_history,
    )

    final_response = ""
    if DEBUG:
        print(f"Response received: {response}")
    if response:
        final_response = response.choices[0].message.content.strip()
        # Clean up artifacts in text
        final_response = re.sub(r"---.*?---", "", final_response).replace("`", "").replace("---", "").replace("BEGIN TEXT", "").replace("END TEXT", "").strip()
        final_response = '\n'.join(re.findall(r".*(\[.*)", final_response.replace("*", "").replace('"', "")))
        conversation_history.append(
            {"role": "assistant", "content": final_response}
        )
    else:
        print("ERROR: No response received!")

    return final_response

# Function: Estimate token count
def estimate_token_count(prompt:str=""):
    prompt_tokens = len(prompt)
    response_tokens = prompt_tokens
    return prompt_tokens + response_tokens

def process_translation(list_original:list=[], DEBUG:bool=False) -> list:
    import langdetect
    def split_chunks(segments:list=[], chunk_size:int=10):
        if chunk_size <= 0:
            raise ValueError("Chunk size must be greater than 0.")
        return [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]

    list_translate = []
    text_original = ""
    for i, segment in enumerate(list_original):
        text_original += f'[{i}] {segment.text}\n'
    text_original = text_original.strip()

    # 📌 Detectar idioma del primer segmento
    first_text = list_original[0].text if list_original else ""
    try:
        language = langdetect.detect(first_text) if first_text else "en"
    except Exception:
        language = "en"

    # 📌 Ajustar tamaño de chunk y reglas según idioma
    if language in ["ja", "ko", "zh-cn", "zh"]:
        CHUNK_SIZE = 12
        extra_rules = (
            "\n7. Maintain subject-predicate-object order as closely as possible.\n"
            "8. You MUST preserve line boundaries to ensure subtitle sync.\n"
        )
    else:
        CHUNK_SIZE = 10
        extra_rules = ""

    # 📌 Armar prompt base
    base_prompt = (
        "You are a professional translator. Translate the text line-by-line following these STRICT RULES:\n"
        "1. **LINE LOCK** - Never merge lines. Each line of the original text becomes exactly one English line, even if mid-sentence.\n"
        "2. **POSITION LOCK** - Maintain original line numbers. [446] must stay [446], [447] stays [447], etc.\n"
        "3. **SPLIT TRANSLATION** - If lines from original text form one sentence, split the English translation across lines using fragments:\n"
        "  * Example Japanese:\n"
        "    - [1] 違う幸せもあることに\n"
        "    - [2] 気づいたんだ\n"
        "  * Example English:\n"
        "    - [1] There exist different types of happiness\n"
        "    - [2] I have come to realize\n\n"
        f"4. **COUNT VERIFICATION** - Final output MUST have exactly {CHUNK_SIZE} lines. Check twice before responding.\n"
        f"5. **STRICT PROHIBITION** - MERGING LINES WILL RESULT IN MEANING LOSS. PRESERVE ALL {CHUNK_SIZE} LINES.\n"
        "6. Provide the translation only, without any additional commentary or explanations.\n"
        f"{extra_rules}"
    )

    chunks = split_chunks(segments=text_original.splitlines(), chunk_size=CHUNK_SIZE)
    print(f"Splitting into {len(chunks)} chunks for translation")
    for chunk in tqdm.tqdm(iterable=chunks, desc="Translating", total=len(chunks)):
        chunk_text = "\n".join(chunk)
        if DEBUG:
            print(f"    Translating chunk of size {len(chunk_text)}")
        terminate = False
        prompt = f'{base_prompt}\n---BEGIN TEXT---\n{chunk_text}\n---END TEXT---'
        RETRIES = 10
        for attempt in range(1, RETRIES+1):
            res = process_llm(user_input=prompt, conversation_history=[])
            list_res = res.splitlines()
            if (len(list_res) != len(chunk)) or not all([len(re.sub(r"\[\w+\]", "", item).strip()) > 0 for item in list_res]):
                if DEBUG:
                    print(f"        Translation {len(list_res)} and chunk {len(chunk)} do not match. Retrying...")
            else:
                break
        if attempt == RETRIES:
            with open(file="prompt.txt", mode="w", encoding="utf-8") as f:
                f.write(prompt)
            with open(file="chunk.txt", mode="w", encoding="utf-8") as f:
                f.write("\n".join(chunk))
            with open(file="res.txt", mode="w", encoding="utf-8") as f:
                f.write(res)
            print("    Failed translation after maximum number of retries. prompt.txt, chunk.txt and res.txt saved for debugging")
            sys.exit(-1)
        for item in list_res:
            try:
                regex_result = re.findall(r".*?\[\w+\].*?[ ]+(.*)", item.strip())
                item_text = regex_result[0] if len(regex_result) > 0 else item.strip()
                if not item_text[0].isupper():
                    item_text = item_text[0].upper() + item_text[1:]
            except Exception as e:
                print("    Chunk translation failed. Terminating loop")
                terminate = True
                break
            if DEBUG:
                print(f"    Translated: {item_text}")
            list_translate.append({"text": item_text})
        if terminate:
            break

    if len(list_original) != len(list_translate):
        print("Bulk translation failed. Translating each segment separately")
        list_translate = []
        for seg in tqdm.tqdm(list_original, total=len(list_original), desc="Translating"):
            prompt = f"{base_prompt}---BEGIN TEXT---\n{seg.text}\n---END TEXT---"
            res = process_llm(prompt, conversation_history=[])
            res = re.sub(r"---.*?---", "", res).strip()
            list_translate.append({"text": res})
    return list_translate
