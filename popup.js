document.getElementById("start-jarvis").addEventListener("click", function() {
    fetch('http://localhost:8000/start')
        .then(response => response.text())
        .then(data => console.log(data))
        .catch(error => console.error('Error:', error));
});
