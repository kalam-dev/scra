document.getElementById('uploadForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    
    const repoUrl = document.getElementById('repoUrl').value;
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    const progressSection = document.getElementById('progressSection');
    const progressBar = document.getElementById('progressBar');
    const progressMessage = document.getElementById('progressMessage');
    
    // Reset UI
    result.innerHTML = '';
    progressSection.classList.add('d-none');
    loading.classList.remove('d-none');
    progressBar.style.width = '0%';
    progressMessage.textContent = 'Starting upload process...';

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ repo_url: repoUrl })
        });
        
        let data;
        try {
            data = await response.json();
        } catch (e) {
            throw new Error(`Server returned invalid JSON: ${await response.text()}`);
        }

        // Update progress based on stage
        if (data.stage === 'download') {
            progressSection.classList.remove('d-none');
            progressBar.style.width = '33%';
            progressMessage.textContent = 'Downloading repository...';
        } else if (data.stage === 'upload') {
            progressSection.classList.remove('d-none');
            progressBar.style.width = '66%';
            progressMessage.textContent = 'Uploading files to Cloudflare R2...';
        } else if (data.stage === 'complete') {
            progressSection.classList.remove('d-none');
            progressBar.style.width = '100%';
            progressMessage.textContent = 'Upload complete!';
        }

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
