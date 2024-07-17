const sendChatBtn = document.querySelector(".chat-input span");
const chatInput = document.querySelector(".chat-input textarea")
const chatbox = document.querySelector(".chatbox")
const chatbotToggler = document.querySelector(".chatbot-toggler")
const chatbotCloseBtn = document.querySelector(".close-btn")

let userMessage;
const inputInitHeight = chatInput.scrollHeight;


const createChatLi = (message, className) => {
    //Creating a <li> element with passed message and classname
    const chatLi = document.createElement("li")
    chatLi.classList.add("chat", className)
    let chatContent = className === "outgoing" ? `<p>${message}</p>` : `<span class="material-symbols-outlined">smart_toy</span><p>${message}</p>`
    chatLi.innerHTML = chatContent;
    return chatLi

}

const handleChat = () => {
    userMessage = chatInput.value.trim();
    if(!userMessage) return;
    chatInput.value=""
    chatInput.style.height = `${inputInitHeight}px`

    // Append the user's message to the chatbox
    chatbox.appendChild(createChatLi(userMessage, "outgoing"));

    setTimeout( ()=> {
        chatbox.appendChild(createChatLi("Thinking...", "incoming"));
    }, 600)

    
}


chatInput.addEventListener("input", () => {
    // Adjust height of input area based on its context
    chatInput.style.height = `${inputInitHeight}px`
    chatInput.style.height = `${chatInput.scrollHeight}px`
})

chatInput.addEventListener("keydown", (e) => {
    if(e.key === "Enter" && !e.shiftKey && window.innerWidth > 800) {
        e.preventDefault()
        handleChat()
    }
})

sendChatBtn.addEventListener("click", handleChat)















chatbotToggler.addEventListener("click", () => {
    document.body.classList.toggle("show-chatbot")
})
chatbotCloseBtn.addEventListener("click", () => {
    document.body.classList.remove("show-chatbot")
})