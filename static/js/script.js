document.getElementById('scrapeForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    
    const websiteUrl = document.getElementById('websiteUrl').value;
    const maxPages = document.getElementById('maxPages').value;
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    const progressSection = document.getElementById('progressSection');
    const progressBar = document.getElementById('progressBar');
    const progressMessage = document.getElementById('progressMessage');
    const pagesProcessed = document.getElementById('pagesProcessed');
    
    // Reset UI
    result.innerHTML = '';
    progressSection.classList.add('d-none');
    loading.classList.remove('d-none');
    progressBar.style.width = '0%';
    progressMessage.textContent = 'Starting scraping process...';
    pagesProcessed.textContent = '';

    try {
        const response = await fetch('/scrape', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ website_url: websiteUrl, max_pages: maxPages })
        });
        
        // Read response body as text first
        const responseText = await response.text();
        let data;

        // Try to parse as JSON
        try {
            data = JSON.parse(responseText);
        } catch (e) {
            throw new Error(`Server returned invalid JSON: ${responseText}`);
        }

        // Update progress based on stage
        progressSection.classList.remove('d-none');
        if (data.stage === 'validation') {
            progressBar.style.width = '0%';
            progressMessage.textContent = 'Validating URL...';
        } else if (data.stage === 'crawl') {
            progressBar.style.width = '33%';
            progressMessage.textContent = 'Crawling website...';
        } else if (data.stage === 'convert') {
            progressBar.style.width = '66%';
            progressMessage.textContent = 'Converting HTML to Markdown...';
        } else if (data.stage === 'upload') {
            progressBar.style.width = '90%';
            progressMessage.textContent = 'Uploading files to Cloudflare R2...';
        } else if (data.stage === 'complete') {
            progressBar.style.width = '100%';
            progressMessage.textContent = 'Scraping and upload complete!';
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
