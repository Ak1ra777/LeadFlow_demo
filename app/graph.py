# app/graph.py
import os
import re
import operator
import psycopg2
from typing import TypedDict, Annotated, List
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.rag import retrieve_info

load_dotenv()

COMPANY_NAME = os.getenv("COMPANY_NAME")
COMPANY_CITY = os.getenv("COMPANY_CITY")
# Database Configuration
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")

# -----------------------------
# Phone normalization + TTS helpers
# -----------------------------

# Output side (for TTS): digits -> Georgian words
DIGIT_TO_KA = {
    "0": "ნული",
    "1": "ერთი",
    "2": "ორი",
    "3": "სამი",
    "4": "ოთხი",
    "5": "ხუთი",
    "6": "ექვსი",
    "7": "შვიდი",
    "8": "რვა",
    "9": "ცხრა",
}

# Input side (from user speech/text): words -> digits
WORD_TO_DIGIT = {
    # English
    "zero": "0", "oh": "0",
    "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",

    # Georgian (common forms)
    "ნული": "0", "ნოლი": "0", "ნოლ": "0",
    "ერთი": "1",
    "ორი": "2",
    "სამი": "3",
    "ოთხი": "4",
    "ხუთი": "5",
    "ექვსი": "6",
    "შვიდი": "7",
    "რვა": "8",
    "ცხრა": "9",
}

def get_db_connection():    
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST
        )
        return conn
    except Exception as e:
        print(f"❌ Database Connection Error on Port: {e}")
        return None

def georgianize_digits_for_tts(text: str) -> str:
    # Replace each digit sequence with Georgian digit-words (digit-by-digit)
    def repl(m):
        s = m.group(0)
        return " ".join(DIGIT_TO_KA.get(ch, ch) for ch in s)
    return re.sub(r"\d+", repl, text)

def normalize_phone_to_digits(phone: str) -> str:
    """Convert spoken digit-words (Georgian/English) -> digits, then keep digits only."""
    t = (phone or "").lower()
    for w, d in WORD_TO_DIGIT.items():
        t = re.sub(rf"\b{re.escape(w)}\b", d, t)
    return re.sub(r"\D", "", t)


# In-memory dedupe for demo (resets on restart)
# Key is (lowercased name, digits-only phone)
LEADS_SAVED: set[tuple[str, str]] = set()


@tool
def save_lead_mock(name: str, phone: str):
    """
    Save the user's contact info as a hot lead (now writes to Postgres).
    Normalizes phone to digits and ignores duplicate saves.
    """
    clean_name = (name or "").strip()
    phone_digits = normalize_phone_to_digits(phone)

    if not clean_name or not phone_digits:
        return "Missing name or phone. Ask again."

    key = (clean_name.lower(), phone_digits)
    if key in LEADS_SAVED:
        return "Lead already saved. Do not save again. End the call."

    conn = get_db_connection()
    if conn is None:
        return "Database error. Tell the user we will call them later."

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leads (name, phone)
                    VALUES (%s, %s)
                    """,
                    (clean_name, phone_digits),
                )
        LEADS_SAVED.add(key)
        print(f"\n🔥 HOT LEAD SAVED TO DB: {clean_name} ({phone_digits}) 🔥\n")
        return "Success. Lead saved. Tell the user the manager will contact them."
    except Exception as e:
        print(f"❌ Lead insert error: {e}")
        return "Database error. Tell the user we will call them later."
    finally:
        try:
            conn.close()
        except Exception:
            pass



@tool
def lookup_policy(query: str):
    """Look up prices, hours, and rules in the company policy knowledge base."""
    return retrieve_info(query)


tools = [lookup_policy, save_lead_mock]
tool_node = ToolNode(tools)

class AgentState(TypedDict):
    messages: Annotated[List, operator.add]

SYSTEM_PROMPT = f"""
შენ ხარ {COMPANY_NAME}-ის პროფესიონალი AI გაყიდვების აგენტი {COMPANY_CITY}-ში, საქართველო.
მისია: ზუსტად უპასუხო კითხვებს და საჭიროების შემთხვევაში შეაგროვო კლიენტის საკონტაქტო ინფორმაცია (სახელი + ტელეფონი).

ძირითადი წესები:
1) ფასებზე, სამუშაო საათებზე და წესებზე პასუხისას ყოველთვის გამოიყენე lookup_policy. არასოდეს გამოიგონო.
2) პასუხი ყოველთვის ქართულად დაწერე (მომხმარებლის ენის მიუხედავად).
3) იყავი მეგობრული, ადამიანური და თავდაჯერებული. ნუ იქნები მომაბეზრებელი ან ზედმეტად დამაჯერებელი.
4) პასუხები მოკლე და გასაგები, სიზუსტე/სიცხადე პრიორიტეტია.
5) უპასუხე მხოლოდ მომხმარებლის შეკითხვას 1–2 წინადადებით. ნუ დაამატებ სხვა დეტალებს, თუ პირდაპირ არ გთხოვა.
6) თუ მომხმარებელი უკვე დაინტერესდა/დათანხმდა, შეწყვიტე „გაყიდვა“ და გადადი მონაცემების შეგროვებაზე.
7) ზარის დასრულებისას ბოლო სტრიქონად ყოველთვის დაწერე ზუსტად ეს ფრაზა (არ შეცვალო არც ერთი სიმბოლო):
   "დიდი მადლობა ზარისთვის {COMPANY_NAME}-ში. ნახვამდის!"

ნაკადი:
A) დახმარებაზე ორიენტირებული საუბარი
- ჯერ უპასუხე lookup_policy-ით.
- შემდეგ ჰკითხე: „კიდევ რით შემიძლია დაგეხმაროთ?“
- თუ მომხმარებელი სთხოვს დამატებით დეტალებს, უპასუხე და ისევ იგივე სტილში გააგრძელე.

B) მონაცემების შეგროვება (დადასტურებით)
- თუ მომხმარებელი დაინტერესდა, თქვი:
  „კარგია. ჩასაწერად მითხარით თქვენი სრული სახელი და ტელეფონის ნომერი.“
- თუ მოიტანა მხოლოდ სახელი:
  „გმადლობთ! თქვენი ტელეფონის ნომერი რა არის?“ (სახელი აღარ იკითხო)
- თუ მოიტანა მხოლოდ ტელეფონი:
  „გასაგებია. თქვენი სრული სახელი რა არის?“ (ტელეფონი აღარ იკითხო)
- როდესაც სახელს მიიღებ:
  გაიმეორე როგორც გაიგე და ჰკითხე: „სწორია?“
- როდესაც ტელეფონს მიიღებ:
  გაიმეორე ნომერი ციფრებით და დაყავი ჯგუფებად (მაგ: 599 123 456) და ჰკითხე: „სწორია?“
- თუ გაურკვეველია, ერთხელ სთხოვე ნელა გაიმეოროს.

C) ლიდის შენახვა
- როგორც კი დააზუსტებ ორივეს B ინსტრუქციის მიხედვით — სრული სახელი და ტელეფონი — დაუყოვნებლივ გამოიძახე save_lead_mock(name, phone).
  (tool call-ში ტელეფონი გაგზავნე მხოლოდ ციფრებით.)
- შემდეგ მოკლედ დაადასტურე:
  „იდეალურია, გმადლობთ! ჩვენი გუნდი მალე დაგიკავშირდებათ.“
- და შემდეგ ზარი დაასრულე წესის #7 ფრაზით (როგორც ბოლო სტრიქონი).

გამოსვლა
- თუ მომხმარებელი ორჯერ უარს იტყვის, ან ითხოვს დასრულებას/ემშვიდობება:
  უპასუხე მოკლედ და დაასრულე წესის #7 ფრაზით (როგორც ბოლო სტრიქონი).
"""



model = ChatOpenAI(model="gpt-4.1-mini", temperature=0.2)
model_with_tools = model.bind_tools(tools)

def agent(state: AgentState):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile()
