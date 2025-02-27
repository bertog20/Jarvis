// Log to confirm content.js is running
console.log("content.js is running");

// Scan for buttons and links on the page
function scanPageElements() {
    const buttons = Array.from(document.getElementsByTagName("button")).map(button => button.id || "Unnamed Button");
    const links = Array.from(document.getElementsByTagName("a")).map(link => link.textContent.trim() || "Unnamed Link");

    console.log("Scanned buttons:", buttons);
    console.log("Scanned links:", links);

    return { buttons, links };
}

// Listen for messages from popup.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.command === "scanElements") {
        console.log("Received 'scanElements' command from popup.js");

        const elements = scanPageElements(); // Scan buttons and links
        sendResponse(elements); // Send the scanned elements back to popup.js
    }
});
