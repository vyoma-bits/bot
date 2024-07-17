import os
import ast
import re
import random
import string
from fastapi import FastAPI,Request,Body, HTTPException, Depends, Header
from pydantic import BaseModel
import httpx
import jwt
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from fastapi import FastAPI, Request, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from langchain.agents.agent_toolkits import create_retriever_tool
from langchain_community.vectorstores import FAISS
from langchain_core.example_selectors import SemanticSimilarityExampleSelector
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import (
    ChatPromptTemplate,
    FewShotPromptTemplate,
    MessagesPlaceholder,
    PromptTemplate,
    SystemMessagePromptTemplate,
)
from langserve import server
from langchain.memory import ConversationBufferMemory
import secrets

SECRET_KEY = secrets.token_hex(32)  # Generates a 64-character hexadecimal string
# Set environment variables
os.environ["OPENAI_API_KEY"] = ""
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["LANGCHAIN_PROJECT"] = "pr-kindly-self-49"

def initialize_database():
    db_uri = ""
    
    # Create the SQLAlchemy engine
    engine = create_engine(db_uri)
    
    db = SQLDatabase(engine)
    
    # Create queries table if it doesn't exist
    create_table_query = """
    CREATE TABLE IF NOT EXISTS queries (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50),
        query TEXT,
        response TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    db.run(create_table_query)
    return db

def initialize_llm():
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    return llm

def query_as_list(db, query):
    res = db.run(query)
    res = [el for sub in ast.literal_eval(res) for el in sub if el]
    res = [re.sub(r"\b\d+\b", "", string).strip() for string in res]
    return list(set(res))

def create_retriever(db):
    products = query_as_list(db, "SELECT name FROM mytable")
    des = query_as_list(db, "SELECT categories FROM mytable")
    vector_db = FAISS.from_texts(products + des, OpenAIEmbeddings())
    retriever = vector_db.as_retriever(search_kwargs={"k": 5})
    description = """Use to look up values to filter on. Input is an approximate spelling of the proper noun, output is valid proper nouns. Use the noun most similar to the search."""
    retriever_tool = create_retriever_tool(
        retriever,
        name="search_proper_nouns",
        description=description,
    )
    return retriever_tool

def initialize_agent(db, llm, retriever_tool):
    system = """
You are an AI-powered marketing agent and SQL database interaction agent for an innovative e-commerce platform based in India. Your primary mission is to engage, inform, and convert customers aged 18-40 who have discovered the website through Instagram advertisements. As a knowledgeable, persuasive, and friendly marketing assistant, your goal is to guide potential customers through the product selection process, highlight special offers, and ultimately drive sales while providing an exceptional customer experience.
Customer Interaction Guidelines
When interacting with customers, remember to:

    Emphasize Unique Selling Points:
        Highlight exclusive product ranges, faster delivery times, innovative features, and any other advantages over competitors.
    Tailor Recommendations:
        Focus on current trends, lifestyle preferences, and cultural nuances specific to the Indian market.
        Make connections between influencer content on Instagram and available products.
    Clear and Concise Information:
        Provide detailed information about product features, prices, and ongoing promotions or discounts.
        Be transparent about pricing, including any applicable taxes or shipping fees.
    Engaging Tone:
        Use a friendly, engaging tone that resonates with the target audience.
        Incorporate appropriate emojis and casual language when suitable, but maintain professionalism.
    Personalized Suggestions:
        Offer personalized product suggestions based on customer preferences, browsing history, or past purchases.
        Create a tailored shopping experience.
    Ease of Purchase:
        Explain the ease of purchase and any customer-friendly policies (e.g., easy returns, fast shipping, cash on delivery options).
    Cross-Selling and Upselling:
        Encourage customers to explore related products or popular items in the store.
    Loyalty Programs:
        Provide information on loyalty programs, referral bonuses, or special member-only discounts.
    Product Authenticity:
        Address concerns about product authenticity, especially for high-end or branded items.
    Guidance on Product Details:
        Offer guidance on size charts, product care instructions, and compatibility information.
    Sale Events:
        Be knowledgeable about ongoing or upcoming sale events (e.g., Diwali sales, End of Season sales).
    Stock Availability:
        Provide information on stock availability and estimated delivery times.
    Payment Options:
        Be knowledgeable about payment options available (e.g., UPI, net banking, EMI) and any bank-specific offers or discounts.
    Customer Service:
        Handle basic customer service queries, such as order tracking, return policies, and general FAQs.
        Escalate complex issues or complaints to human customer service representatives when necessary.
    Feedback and Improvement:
        Collect and analyze customer feedback to improve product recommendations and overall shopping experience.
    Multilingual Support:
        Provide multilingual support if possible, catering to customers who prefer to communicate in languages other than English.
    Abandoned Cart Recovery:
        Assist with abandoned cart recovery by sending reminders and offering incentives to complete purchases.
    Mobile App Promotion:
        Promote the mobile app if available, highlighting its features and any app-exclusive offers.
    Sustainable Products:
        Educate customers about sustainable or eco-friendly product options.
    Competitor Comparison:
        Be prepared to discuss and compare your platform with major competitors in the Indian e-commerce space.

SQL Database Interaction Guidelines
When searching the database or providing product information:

    Use the 'mytable5' Table:
        Access product data efficiently and accurately from the 'mytable' table.
    Accurate Pricing Information:
        Provide accurate pricing information, clearly distinguishing between regular and sale prices.
        Highlight the savings percentage or amount when applicable.
    Discount Calculation:
        Calculate and communicate discounts to highlight savings.
    Best Value Recommendations:
        Recommend products based on best value, considering factors like RAM, price, screen size, processor, and graphics card for electronics.
        For other categories, focus on relevant features such as material quality, brand reputation, or customer ratings.
    Default Recommendations:
        If a customer doesn't specify requirements, suggest products with the best features and competitive pricing as a default.
    Limit Query Results:
        Limit query results to a reasonable number (e.g., top 5 to 10) to avoid overwhelming the customer.
    Product Comparison:
        Be prepared to compare products side-by-side, highlighting key differences in features, price, and value proposition.
    Stock and Delivery Information:
        Provide information on stock availability and estimated delivery times.
    Alternatives for Out-of-Stock Items:
        Offer alternatives or waitlist options for out-of-stock items.
    Payment Options:
        Be knowledgeable about payment options available and any bank-specific offers or discounts.    """
    prompt = ChatPromptTemplate.from_messages(
        [("system", system), ("human", "{input}"), MessagesPlaceholder("agent_scratchpad")]
    )
    agent = create_sql_agent(
        llm=llm,
        db=db,
        extra_tools=[retriever_tool],
        prompt=prompt,
        agent_type="openai-tools",
        verbose=True,
    )
    return agent

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

db = initialize_database()
llm = initialize_llm()
retriever_tool = create_retriever(db)
agent = initialize_agent(db, llm, retriever_tool)

def generate_user_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat")
async def chat(request: Request, payload: dict = Body(...)):
    user_input = payload["message"]
    user_id = payload.get("user_id", generate_user_id())
    response = agent.run(user_input)
    
    # Store query and response in the database
    db.run(f"INSERT INTO queries (user_id, query, response) VALUES ('{user_id}', '{user_input}', '{response}')")
    
    return {"response": response, "user_id": user_id}
"""Code modified from below"""
gkey = "86c9abe0-f0a8-4230-9fce-ba54a70c538f"
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZGVudGlmaWVyIjoyNjk1fQ.kSE16TbPskzEm1mX_RrIlXqWkF97pI9JzkOjVMsXl-Y"


app = FastAPI()

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# # In-memory store for OTPs
# otp_store: Dict[str, str] = {}
# print(otp_store)

# # Model for phone number input
# class PhoneNumberInput(BaseModel):
#     phoneNumber: str

# Model for email input
class emailInput(BaseModel):
    email: str

# Model for OTP verification input
class OTPInput(BaseModel):
    phoneNumber: str
    otp: str

# def generate_otp() -> str:
#     return str(random.randint(1000, 9999))


# async def send_otp_via_whatsapp(phone_number: str, otp: str) -> None:
#     whatsapp_api_url = "https://api.yourwhatsappservice.com/send"  # Change this to your WhatsApp API endpoint
#     api_key = "YOUR_WHATSAPP_API_KEY"  # Replace with your WhatsApp API key

#     message = f"Your OTP is {otp}. Please use this to verify your number."
#     data = {
#         "phone": phone_number,
#         "body": message,
#     }
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {api_key}",
#     }

#     async with httpx.AsyncClient() as client:
#         response = await client.post(whatsapp_api_url, json=data, headers=headers)
#         response.raise_for_status()


# def create_jwt_token(phone_number: str) -> str:
#     payload = {
#         "phone_number": phone_number,
#         "exp": time.time() + 3600  # Token expiration time (e.g., 1 hour)
#     }
#     token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
#     return token

def verify_jwt_token(authorization: str = Header(...)) -> str:
    try:
        token = authorization.split(" ")[1]  # Get the token from the "Bearer" prefix
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    



# @app.post("/send-otp")
# async def send_otp(phone_number_input: PhoneNumberInput):
#     """ The phone number is stored over here please use this to push to the db """
#     phone_number = phone_number_input.phoneNumber
#     otp = generate_otp()
#     otp_store[phone_number] = otp
#     print(otp_store)


#     print(otp_store)


#     try:
#         # await send_otp_via_whatsapp(phone_number, otp)
#         print(phone_number, otp)
#         return {"success": True, "message": "OTP sent successfully"}
#     except httpx.HTTPStatusError as e:
#         raise HTTPException(status_code=500, detail="Failed to send OTP")


# @app.post("/verify-otp")
# async def verify_otp(otp_input: OTPInput):
#     phone_number = otp_input.phoneNumber
#     user_otp = otp_input.otp
#     stored_otp = otp_store.get(phone_number)

#     if stored_otp and stored_otp == user_otp:
#         del otp_store[phone_number]  # OTP verified, remove from store
#         token = create_jwt_token(phone_number)
#         print(token)
#         return {"success": True, "message": "OTP verified successfully", "token": token}
#     else:
#         raise HTTPException(status_code=400, detail="Incorrect OTP")



@app.get("/protected-route")
async def protected_route(token: str = Depends(verify_jwt_token)):
    return {"success": True, "message": f"Access granted for {token}"}




class EmailInput(BaseModel):
    email: str

class OtpInput(BaseModel):
    otp_id: str
    otp: str

@app.post("/send-mail-otp")
async def send_otp(email_input: EmailInput):
    url = 'https://api.fazpass.com/v1/otp/request'
    payload = {'email': email_input.email, 'gateway_key': gkey}
    headers = {
        'Authorization': f'Bearer {BEARER_TOKEN}'
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)


@app.post("/verify-mail-otp")
async def send_otp(otp_input: OtpInput):
    url = 'https://api.fazpass.com/v1/otp/verify'
    payload = {'otp_id': otp_input.otp_id, 'otp' : otp_input.otp}
    headers = {
        'Authorization': f'Bearer {BEARER_TOKEN}'
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            # Create a JWT token with the payload and secret key
            token_payload = {'otp_id': otp_input.otp_id, 'otp': otp_input.otp}
            token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")

            # Get the response data from the OTP verification API
            response_data = response.json()

            # Include the JWT token in the response
            response_data['token'] = token

            return response_data
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id = generate_user_id()
    try:
        while True:
            data = await websocket.receive_text()
            response = agent.run(data)
            
            # Store query and response in the database
            db.run(f"INSERT INTO queries (user_id, query, response) VALUES ('{user_id}', '{data}', '{response}')")
            
            await websocket.send_text(response)
    except WebSocketDisconnect:
        pass
            
          
