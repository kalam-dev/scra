document.getElementById('uploadForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    
    const repoUrl = document.getElementById('repoUrl').value;
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    
    // Reset UI
    result.innerHTML = '';
    loading.classList.remove('d-none');

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ repo_url: repoUrl })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            result.innerHTML = `
                <div class="alert alert-success">
                    ${data.message}
                    <ul>
                        ${data.files.map(file => `<li>${file}</li>`).join('')}
                    </ul>
                </div>
            `;
        } else {
            result.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
        }
    } catch (error) {
        result.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    } finally {
        loading.classList.add('d-none');
    }
});
