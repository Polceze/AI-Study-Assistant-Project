// Application state
let flashcardsData = [];
let hasSavedCurrentSet = false;
let allSessions = [];
let currentPage = 1;
const sessionsPerPage = 5;
let progressChart = null;
let currentUser = null;

// function to limit how often setUniformCardHeights runs during resizing
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    console.log('AI Study Buddy loaded successfully!');
    
    // Initialize card flip functionality
    const flashcardElements = document.querySelectorAll('.flashcard');
    flashcardElements.forEach(card => {
        card.addEventListener('click', function() {
            this.classList.toggle('flipped');
        });
    });
    
    // Generate studycards button
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) {
        generateBtn.addEventListener('click', generateFlashcards);
    }

    // Resize event listener for flashcard heights
    window.addEventListener('resize', debounce(setUniformCardHeights, 200));
    
    // Save studycards button - INITIALIZE TO DISABLED STATE
    const saveBtn = document.getElementById('save-btn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Save study session';
        saveBtn.title = 'Generate studycards first';
        saveBtn.addEventListener('click', saveFlashcards);
    }
    
    // Load sessions with pagination - BUT WAIT FOR AUTH TO COMPLETE
    initAuth().then(isAuthenticated => {
        if (isAuthenticated) {
            loadSessions(1); // Load first page only after auth completes
        } else {
            // User not authenticated, show appropriate message
            const container = document.getElementById('sessions-container');
            container.innerHTML = '<p class="no-sessions">Please sign in to view your study sessions</p>';
            
            // Clear the chart and stats for logged out users
            updateProgressChart([], 5);
            updateSummaryStats([]);
        }
    });
    
    // Chart range selector event listener
    const rangeSelector = document.getElementById('sessions-range');
    if (rangeSelector) {
        // Set default value to 5
        rangeSelector.value = '5';
        
        rangeSelector.addEventListener('change', function() {
            const limit = this.value === 'all' ? allSessions.length : parseInt(this.value);
            updateProgressChart(allSessions, limit);
        });
    }

    const sameNotesBtn = document.getElementById('new-session-same-notes');
    const clearNotesBtn = document.getElementById('new-session-clear-notes');
    
    if (sameNotesBtn) {
        sameNotesBtn.addEventListener('click', function() {
            resetUIForNewSession(false); // Keep notes
            document.getElementById('generate-btn').focus();
        });
    }
    
    if (clearNotesBtn) {
        clearNotesBtn.addEventListener('click', function() {
            resetUIForNewSession(true); // Clear notes
            document.getElementById('study-notes').focus();
        });
    }
    
    // Success modal option listeners
    const continueSameBtn = document.getElementById('continue-same-notes');
    const startFreshBtn = document.getElementById('start-fresh');
    const stayInSessionBtn = document.getElementById('view-progress');
    
    if (continueSameBtn) {
        continueSameBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            console.log('Continue with Same Notes clicked');
            clearFlashcardsUI(); // Clear flashcards for new session
            resetUIForNewSession(false); // Keep notes
            document.getElementById('generate-btn').focus();
        });
    }
    
    if (startFreshBtn) {
        startFreshBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            console.log('Start Fresh clicked');
            clearFlashcardsUI(); // Clear flashcards for new session
            resetUIForNewSession(true); // Clear notes
            document.getElementById('study-notes').focus();
        });
    }
    
    if (stayInSessionBtn) {
        stayInSessionBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            console.log('Stay in This Session clicked');
            stayInSession(); // Only hide modal, preserve all UI
        });
    }

    // Initialize auth
    initAuth();

    // Add event listener for the modal's close button
    const modalCloseBtn = document.getElementById('modal-close-btn');
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', closeSessionModal);
    }

    // Add event listener for the modal's delete button (basic version for Phase 2)
    const modalDeleteBtn = document.getElementById('modal-delete-session-btn');
    if (modalDeleteBtn) {
        modalDeleteBtn.addEventListener('click', function() {
            const sessionId = this.getAttribute('data-session-id');
            if (!sessionId) {
                alert("No session selected for deletion");
                return;
            }
            
            // Show confirmation dialog (as requested)
            const confirmDelete = confirm("Are you sure you want to delete this session?\nThis action cannot be undone.");
            
            if (confirmDelete) {
                deleteSessionFromModal(sessionId);
            }
        });
    }

    // Event listener for logo refresh-page
    const logo = document.querySelector('.logo');
    if (logo) {
        logo.addEventListener('click', function() {
            window.location.reload();
        });
    }

     // Add upgrade button listener
    const upgradeBtn = document.getElementById('upgrade-page-btn');
    if (upgradeBtn) {
        upgradeBtn.addEventListener('click', navigateToUpgrade);
    }

    // Initialize mobile menu functionality
    setTimeout(() => {
        const isInitialized = initMobileMenu();
        if (!isInitialized) {
            console.log('Mobile menu not initialized yet, will retry after auth');
        }
    }, 1000); // Give the page time to load completely

    // Add event listeners for NEW mobile menu buttons
    const mobileUpgradeBtn = document.getElementById('mobile-upgrade-page-btn');
    if (mobileUpgradeBtn) {
        mobileUpgradeBtn.addEventListener('click', function() {
            navigateToUpgrade();
        });
    }

    const mobileLogoutBtn = document.getElementById('mobile-logout-btn');
    if (mobileLogoutBtn) {
        mobileLogoutBtn.addEventListener('click', function() {
            handleLogout();
        });
    }

});

// Delegate click events for dynamically created "View" buttons
document.addEventListener('click', function(e) {
    // Check if a "View" button was clicked
    if (e.target.classList.contains('view-session-btn')) {
        const sessionId = e.target.getAttribute('data-id');
        openSessionModal(sessionId);
    }
});

// Generate studycards function
function generateFlashcards() {
    // Reset save state when generating new studycards
    hasSavedCurrentSet = false;
    
    const notes = document.getElementById('study-notes').value;
    const count = parseInt(document.getElementById('num-questions').value);
    
    if (!notes) {
        alert('Please enter some study notes first.');
        return;
    }
    
    if (count < 1 || count > 13) {
        alert('Please enter a number between 1 and 12 for the number of questions.');
        return;
    }
    
    // Show loading animation
    const loader = document.getElementById('loader');
    const generateBtn = document.getElementById('generate-btn');
    const saveBtn = document.getElementById('save-btn');
    
    loader.style.display = 'block';
    generateBtn.disabled = true;
    
    // Send request to backend
    fetch('/generate_questions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            notes: notes,
            num_questions: count
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            flashcardsData = data.questions.map(q => ({
                ...q,
                userAnswer: null,
                answered: false
            }));
            
            displayFlashcards();
            
            // Enable save button for new studycards
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save study session';
            hasSavedCurrentSet = false;
            saveBtn.title = 'Save your current session to your study history';
            
            // Show AI status message
            const statusMessage = document.getElementById('ai-status');
            if (statusMessage) {
                statusMessage.textContent = data.message || 
                    (data.source === 'ai' ? 'Questions generated by AI' : 'Using sample questions');
                statusMessage.className = `ai-status ${data.source}`;
            }
            
        } else {
            alert('Error generating questions: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error generating questions');
    })
    .finally(() => {
        loader.style.display = 'none';
        generateBtn.disabled = false;
    });
}

// Update Save Button state function definition
function updateSaveButtonState() {
    const saveBtn = document.getElementById('save-btn');
    if (!saveBtn) return;
    
    if (hasSavedCurrentSet) {
        // Already saved current set - keep disabled
        saveBtn.disabled = true;
        saveBtn.textContent = '✓ Saved';
        saveBtn.title = 'studycards saved! Generate new studycards to save another set.';
    } else if (flashcardsData && flashcardsData.length > 0) {
        // Have studycards, check if all are answered
        const unanswered = flashcardsData.filter(card => 
            card.userAnswer === null || card.userAnswer === undefined
        ).length;
        
        saveBtn.disabled = unanswered > 0;
        saveBtn.textContent = 'Save study session';
        saveBtn.title = unanswered > 0 ? 
            `Please answer all ${unanswered} questions before saving` : 
            'Save your current session to your study history';
    } else {
        // No studycards generated yet OR page just loaded
        saveBtn.disabled = true;
        saveBtn.textContent = 'Save study session';
        saveBtn.title = 'Generate studycards first';
    }
}

// Function to set uniform card heights
function setUniformCardHeights() {
    const flashcards = document.querySelectorAll('.flashcard');
    if (flashcards.length === 0) {
        console.log('No flashcards to resize');
        return;
    }
    
    console.log('Adjusting flashcard heights');
    let maxHeight = 0;
    
    // Reset heights to auto to get accurate measurements
    flashcards.forEach(card => {
        card.style.height = 'auto';
    });
    
    // Find the maximum height
    flashcards.forEach(card => {
        const front = card.querySelector('.flashcard-front');
        const back = card.querySelector('.flashcard-back');
        
        // Use the taller of the two sides
        const cardHeight = Math.max(
            front.scrollHeight, 
            back.scrollHeight
        );
        
        if (cardHeight > maxHeight) {
            maxHeight = cardHeight;
        }
    });
    
    // Add padding to the max height
    maxHeight += 20;
    
    // Apply the maximum height to all cards
    flashcards.forEach(card => {
        card.style.height = `${maxHeight}px`;
    });
    console.log(`Set uniform height to ${maxHeight}px for ${flashcards.length} flashcards`);
}

// Display studycards function
function displayFlashcards() {
    const flashcardsContainer = document.getElementById('flashcards-container');
    const scoreContainer = document.getElementById('score-container');
    
    flashcardsContainer.innerHTML = '';
    scoreContainer.textContent = 'Score: 0/0 (0%)';
    
    flashcardsData.forEach((card, index) => {
        const flashcardEl = document.createElement('div');
        flashcardEl.className = 'flashcard';
        flashcardEl.setAttribute('data-index', index);
        
        flashcardEl.innerHTML = `
            <div class="flashcard-inner">
                <div class="flashcard-front">
                    <div class="question">${card.question}</div>
                    <div class="options">
                        ${card.options.map((option, optIndex) => `
                            <div class="option" data-option="${optIndex}">
                                ${String.fromCharCode(65 + optIndex)}) ${option}
                            </div>
                        `).join('')}
                    </div>
                    <div class="instructions">Select an answer, then click to flip</div>
                </div>
                <div class="flashcard-back">
                    <div class="question">${card.question}</div>
                    <div class="feedback" id="feedback-${index}"></div>
                    <div class="instructions">Click to return to question</div>
                </div>
            </div>
        `;
        
        flashcardsContainer.appendChild(flashcardEl);
        
        // Add event listeners for option selection
        const optionEls = flashcardEl.querySelectorAll('.option');
        optionEls.forEach(optionEl => {
            optionEl.addEventListener('click', function(e) {
                e.stopPropagation();
                const cardIndex = parseInt(flashcardEl.getAttribute('data-index'));
                const optionIndex = parseInt(this.getAttribute('data-option'));
                selectAnswer(cardIndex, optionIndex);
            });
        });
        
        // Add flip functionality
        flashcardEl.addEventListener('click', function() {
            const cardIndex = parseInt(this.getAttribute('data-index'));
            const card = flashcardsData[cardIndex];
            
            if (card.userAnswer === null) {
                alert('Please select an answer first.');
                return;
            }
            
            if (!card.answered) {
                card.answered = true;
                updateCardUI(cardIndex);
                updateScore();
                flashcardEl.classList.add('revealed');
            }
            
            this.classList.toggle('flipped');
        });
    });
    
    setUniformCardHeights(); // Call directly instead of timeout
    updateSaveButtonState();
}


// Function whenever answers change
function selectAnswer(cardIndex, optionIndex) {
    const card = flashcardsData[cardIndex];
    if (card.answered) return;
    
    card.userAnswer = optionIndex;
    
    const flashcardEl = document.querySelector(`.flashcard[data-index="${cardIndex}"]`);
    const optionEls = flashcardEl.querySelectorAll('.option');
    
    optionEls.forEach(el => el.classList.remove('selected'));
    optionEls[optionIndex].classList.add('selected');
    
    // Update save button state when answers change
    updateSaveButtonState();
}

// Update card UI after answer is revealed
function updateCardUI(cardIndex) {
    const card = flashcardsData[cardIndex];
    const flashcardEl = document.querySelector(`.flashcard[data-index="${cardIndex}"]`);
    const optionEls = flashcardEl.querySelectorAll('.option');
    const feedbackEl = document.getElementById(`feedback-${cardIndex}`);
    
    optionEls.forEach((el, index) => {
        if (index === card.correctAnswer) {
            el.classList.add('correct');
        }
        if (index === card.userAnswer) {
            if (index === card.correctAnswer) {
                el.classList.add('correct');
                feedbackEl.textContent = "Correct! ✅";
                feedbackEl.className = "feedback correct";
            } else {
                el.classList.add('incorrect');
                feedbackEl.textContent = "Incorrect! ❌";
                feedbackEl.className = "feedback incorrect";
            }
        }
    });
}

// Update score function
function updateScore() {
    const answeredCount = flashcardsData.filter(card => card.answered).length;
    const totalCount = flashcardsData.length;
    
    if (answeredCount < totalCount) {
        // Show progress, not score
        document.getElementById('score-container').textContent = 
            `Progress: ${answeredCount}/${totalCount} answered`;
    } else {
        // All answered, show actual score
        const correctCount = flashcardsData.filter(card => 
            card.userAnswer === card.correctAnswer
        ).length;
        const percentage = Math.round((correctCount / totalCount) * 100);
        document.getElementById('score-container').textContent = 
            `Score: ${correctCount}/${totalCount} (${percentage}%)`;
    }
}

// Save studycards function
function saveFlashcards() {
    // Prevent saving if already saved
    if (hasSavedCurrentSet) {
        alert('This session has already been saved. Generate new studycards to start a new session.');
        return;
    }
    
    const notes = document.getElementById('study-notes').value;
    
    if (flashcardsData.length === 0) {
        alert('No session to save! Please generate some studycards first.');
        return;
    }
    
    const unanswered = flashcardsData.filter(card => card.userAnswer === null);
    if (unanswered.length > 0) {
        alert(`Please answer all ${unanswered.length} unanswered questions before saving.`);
        return;
    }

    const unrevealed = flashcardsData.filter(card => !card.answered).length;
    if (unrevealed > 0) {
        alert(`Please reveal all ${unrevealed} answers before saving.`);
        return;
    }
    
    const saveBtn = document.getElementById('save-btn');
    const originalText = saveBtn.textContent;
    saveBtn.textContent = 'Saving...';
    saveBtn.disabled = true;
    
    fetch('/save_flashcards', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            flashcards: flashcardsData,
            notes: notes
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Mark as saved and update UI
            handleSaveSuccess();

        } else {
            alert('Error saving session: ' + data.message);
            saveBtn.disabled = false;
        }

    
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error saving session');
        saveBtn.disabled = false;
    })
    .finally(() => {
        if (!hasSavedCurrentSet) {
            saveBtn.textContent = originalText;
        }
    });
}

function initProgressChart() {
    const canvas = document.getElementById('progress-chart');
    if (!canvas) {
        return null;
    }

    const ctx = canvas.getContext('2d');

    progressChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Score (%)',
                    data: [],
                    borderColor: '#6e8efb',
                    backgroundColor: 'rgba(110, 142, 251, 0.1)',
                    yAxisID: 'y',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: 'Number of Questions',
                    data: [],
                    borderColor: '#a777e3',
                    backgroundColor: 'rgba(167, 119, 227, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.3,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Score (%)'
                    },
                    min: 0,
                    max: 100
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Questions'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    });

    return progressChart;
}


function updateProgressChart(sessions, limit = 5) {  // Default is 5
    // Ensure chart exists
    if (!progressChart) {
        progressChart = initProgressChart();
        if (!progressChart) return; // No chart on this page
    }

    if (!sessions || sessions.length === 0) {
        // Clear chart if no data
        progressChart.data.labels = [];
        progressChart.data.datasets[0].data = [];
        progressChart.data.datasets[1].data = [];
        progressChart.update();
        return;
    }

    // Sort by date descending (most recent first) and take the last 'limit' sessions
    const sortedSessions = sessions
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .slice(0, limit);

    // Reverse for chart to show chronological order left to right
    const chartSessions = [...sortedSessions].reverse();

    const labels = chartSessions.map(session =>
        new Date(session.created_at).toLocaleDateString()
    );

    const scores = chartSessions.map(session => session.score_percentage);
    const questionCounts = chartSessions.map(session => session.total_questions);

    progressChart.data.labels = labels;
    progressChart.data.datasets[0].data = scores;
    progressChart.data.datasets[1].data = questionCounts;
    progressChart.update();
}


// Load saved sessions
function loadSessions(page = 1) {
    console.log('🔍 Loading sessions from /list_sessions...');

    // Check if user is authenticated first
    if (!currentUser) {
        console.log('⚠️  User not authenticated, skipping session load');
        const container = document.getElementById('sessions-container');
        container.innerHTML = '<p class="no-sessions">Please sign in to view your study sessions</p>';
        
        // Clear the chart and stats for logged out users
        updateProgressChart([], 5);
        updateSummaryStats([]);
        return;
    }
    
    fetch('/list_sessions')
        .then(response => {
            if (response.status === 401) {
                showAuthModal();
                throw new Error('Authentication required');
            }
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('📊 Sessions data received:', data);
            
            if (data.status === 'success') {
                allSessions = data.sessions;
                console.log(`✅ Found ${allSessions.length} total sessions for user`);
                
                // Always update summary stats, even if empty
                updateSummaryStats(allSessions);
                
                if (allSessions.length === 0) {
                    const container = document.getElementById('sessions-container');
                    container.innerHTML = '<p class="no-sessions">No study sessions yet.</p>';
                    
                    // Clear the chart for users with no sessions
                    updateProgressChart([], 5);
                    return;
                }
                
                renderPaginatedSessions();
                updateProgressChart(allSessions, 5);
                
            } else {
                console.error('❌ Error loading sessions:', data.message);
                const container = document.getElementById('sessions-container');
                container.innerHTML = '<p class="no-sessions">No study sessions found yet.</p>';
                
                // Clear the chart and stats on error
                updateProgressChart([], 5);
                updateSummaryStats([]);
            }
        })
        .catch(error => {
            console.error('❌ Error fetching sessions:', error);
            const container = document.getElementById('sessions-container');
            if (error.message.includes('Authentication')) {
                container.innerHTML = '<p class="no-sessions">Please sign in to view your study sessions</p>';
            } else {
                container.innerHTML = '<p class="no-sessions">Error loading sessions. Please try again.</p>';
            }
            
            // Clear the chart and stats on error
            updateProgressChart([], 5);
            updateSummaryStats([]);
        });
}


// Render paginated sessions
function renderPaginatedSessions() {
    const container = document.getElementById("sessions-container");
    const pagination = document.getElementById("pagination-controls");
    if (!container || !pagination) {
        return;
    }

    // Sort sessions by most recent first
    const sortedSessions = [...allSessions].sort((a, b) => 
        new Date(b.created_at) - new Date(a.created_at)
    );
    
    const startIndex = (currentPage - 1) * sessionsPerPage;
    const endIndex = startIndex + sessionsPerPage;
    const paginatedSessions = sortedSessions.slice(startIndex, endIndex);
    
    renderSessions(paginatedSessions);
    renderPaginationControls();
}


// Render pagination controls
function renderPaginationControls() {
    const totalPages = Math.ceil(allSessions.length / sessionsPerPage);
    const paginationContainer = document.getElementById('pagination-controls');
    
    if (allSessions.length <= sessionsPerPage) {
        paginationContainer.innerHTML = '';
        return;
    }
    
    paginationContainer.innerHTML = `
        <button class="pagination-btn" onclick="changePage(${currentPage - 1})" 
                ${currentPage === 1 ? 'disabled' : ''}>
            ← Previous
        </button>
        
        <span class="pagination-info">
            Page ${currentPage} of ${totalPages} (${allSessions.length} total sessions)
        </span>
        
        <button class="pagination-btn" onclick="changePage(${currentPage + 1})" 
                ${currentPage === totalPages ? 'disabled' : ''}>
            Next →
        </button>
    `;
}

// Pagination button to use already-loaded data, doesn't fetch again
function changePage(page) {
    if (page < 1 || page > Math.ceil(allSessions.length / sessionsPerPage)) return;
    currentPage = page;
    renderPaginatedSessions(); 
}

// Summary Statistics
function updateSummaryStats(sessions) {
    const avgScoreEl = document.getElementById("average-score");
    const totalQuestionsEl = document.getElementById("total-questions");
    const sessionsCountEl = document.getElementById("sessions-count");

    if (!avgScoreEl || !totalQuestionsEl || !sessionsCountEl) {
        return;
    }

    if (!sessions || sessions.length === 0) {
        avgScoreEl.textContent = "0%";
        totalQuestionsEl.textContent = "0";
        sessionsCountEl.textContent = "0";
        return;
    }

    const totalSessions = sessions.length;
    const totalQuestions = sessions.reduce((sum, s) => sum + s.total_questions, 0);
    const avgScore =
        sessions.reduce((sum, s) => sum + (s.score_percentage || 0), 0) / totalSessions;

    avgScoreEl.textContent = `${avgScore.toFixed(1)}%`;
    totalQuestionsEl.textContent = totalQuestions;
    sessionsCountEl.textContent = totalSessions;
}


// Fuction to Render Sessions
function renderSessions(sessions) {
    const container = document.getElementById('sessions-container');
    if (!container) {
        return;
    }

    container.innerHTML = '';

    if (!Array.isArray(sessions)) {
        console.error('❌ renderSessions expected array but got:', sessions);
        container.innerHTML = '<p class="error">Invalid session data format</p>';
        return;
    }

    if (sessions.length === 0) {
        if (typeof currentPage !== "undefined" && currentPage > 1) {
            container.innerHTML = '<p>No more sessions on this page.</p>';
        } else {
            container.innerHTML = '<p>No saved sessions yet.</p>';
        }
        return;
    }

    const list = document.createElement('ul');
    list.className = 'sessions-list';

    sessions.forEach(session => {
        const item = document.createElement('li');
        item.className = 'session-item';

        item.innerHTML = `
            <div class="session-content">
                <div class="session-topic">${session.title}</div>
            </div>
            <div class="session-stats">
                <div class="session-stat session-questions">
                    <span class="session-stat-label">Questions:</span>
                    <span class="session-stat-value">${session.total_questions}</span>
                </div>
                <div class="session-stat session-score">
                    <span class="session-stat-label">Score:</span>
                    <span class="session-stat-value">${session.score_percentage}%</span>
                </div>
            </div>
            <div class="session-actions">
                <button class="view-session-btn" data-id="${session.id}">View</button>
                <button class="delete-session-btn" data-id="${session.id}">Delete</button>
            </div>
        `;

        list.appendChild(item);
    });

    container.appendChild(list);

    // Attach delete listeners
    const deleteButtons = container.querySelectorAll('.delete-session-btn');
    deleteButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const sessionId = btn.getAttribute('data-id');
            deleteSession(sessionId);
        });
    });
}


// Filter sessions by search term
function filterSessions(searchTerm) {
    if (!searchTerm.trim()) {
        renderPaginatedSessions();
        return;
    }
    
    const filtered = allSessions.filter(session => 
        session.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        session.created_at.toLowerCase().includes(searchTerm.toLowerCase())
    );
    
    renderSessions(filtered.slice(0, sessionsPerPage));
    
    // Hide pagination when searching
    document.getElementById('pagination-controls').innerHTML = 
        filtered.length > 0 ? 
        `<p>Showing ${filtered.length} matching sessions</p>` : 
        `<p>No sessions match "${searchTerm}"</p>`;
}

// Delete a session 
function deleteSession(sessionId) {
    if (!confirm("Are you sure you want to delete this session?\nThis action cannot be undone.")) return;

    fetch(`/delete_session/${sessionId}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Reload sessions but stay on current page
                loadSessions(currentPage);
                showTempMessage("Session deleted successfully", "success");
            } else {
                alert('Error deleting session: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error deleting session:', error);
            alert('Error deleting session');
        });
}

function attemptAutoLogin(email) {
    return fetch('/auth/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: email })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            setUserAuthenticated(data.user);
            hideAuthModal();
            return true; // Return true for success
        } else {
            showAuthModal();
            return false; // Return false for failure
        }
    })
    .catch(error => {
        console.error('Auto-login failed:', error);
        showAuthModal();
        return false; // Return false for failure
    });
}

// Check if user was previously authenticated
function checkSavedAuth() {
    return new Promise((resolve) => {
        const savedEmail = localStorage.getItem('userEmail');
        const savedUserId = localStorage.getItem('userId');
        
        if (!savedEmail || !savedUserId) {
            showAuthModal();
            resolve(false); // Resolve with false for not authenticated
            return;
        }

        // First check if we already have a valid session
        fetch('/auth/status')
            .then(response => response.json())
            .then(data => {
                if (data.authenticated && data.user) {
                    // We have a valid session
                    setUserAuthenticated(data.user);
                    hideAuthModal();
                    resolve(true); // Resolve with true for authenticated
                } else {
                    // Session expired, try to re-login
                    attemptAutoLogin(savedEmail).then(resolve);
                }
            })
            .catch(error => {
                console.error('Auth status check failed:', error);
                attemptAutoLogin(savedEmail).then(resolve);
            });
    });
}

// Initialize auth (non-blocking initially)
function initAuth() {
    setupAuthEventListeners();
    return checkSavedAuth(); 
}

function setupAuthEventListeners() {
    // Auth submit
    document.getElementById('auth-submit').addEventListener('click', handleLogin);
    
    // Enter key in email field
    document.getElementById('auth-email').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            handleLogin();
        }
    });
    
    // Logout
    document.getElementById('logout-btn').addEventListener('click', handleLogout);
}

function setUserAuthenticated(user) {
    currentUser = user;
    
    // Update UI elements
    const topbarEmail = document.getElementById('topbar-email');
    const mobileTopbarEmail = document.getElementById('mobile-topbar-email');
    const authTopbar = document.getElementById('auth-topbar');
    
    if (topbarEmail) topbarEmail.textContent = user.email;
    if (mobileTopbarEmail) mobileTopbarEmail.textContent = user.email;
    if (authTopbar) authTopbar.style.display = 'block';
    
    document.body.classList.add('has-topbar');
    localStorage.setItem('userEmail', user.email);
    localStorage.setItem('userId', user.id);

    // Enable app interface but make sure save button is in correct state
    enableAppInterface();
    
    // Explicitly set save button to disabled state initially
    const saveBtn = document.getElementById('save-btn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Save study session';
        saveBtn.title = 'Generate studycards first';
    }

    // Clear old sessions data and reset stats
    allSessions = [];
    updateProgressChart(allSessions, 5);
    updateSummaryStats(allSessions);
    
    // Update tier information
    updateTierInfo();
    
    // Load sessions - but only after a brief delay to ensure auth is fully processed
    setTimeout(() => {
        loadSessions(1);
    }, 100);
    
    // Set interval to update tier info every minute
    setInterval(updateTierInfo, 60000);
}

function handleLogin() {
    const email = document.getElementById('auth-email').value.trim();
    
    if (!email || !email.includes('@')) {
        alert('Please enter a valid email address');
        return;
    }
    
    const submitBtn = document.getElementById('auth-submit');
    submitBtn.textContent = 'Signing in...';
    submitBtn.disabled = true;
    
    fetch('/auth/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: email })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            setUserAuthenticated(data.user);
            hideAuthModal();
            localStorage.setItem('userEmail', data.user.email);
            localStorage.setItem('userId', data.user.id);
            // Button will be re-enabled by enableAppInterface()
        } else {
            alert('Login failed: ' + data.message);
            resetAuthButton(); // Use the reset function
        }
    })
    .catch(error => {
        console.error('Login error:', error);
        alert('Login failed. Please try again.');
        resetAuthButton(); // Use the reset function
    });
}

function handleLogout() {
    // Get the submit button and reset it FIRST
    const submitBtn = document.getElementById('auth-submit');
    resetAuthButton(); // Reset button state immediately
    
    fetch('/auth/logout')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Remove user indicator
                const indicator = document.getElementById('user-indicator');
                if (indicator) indicator.remove();
                
                // Reset app state
                currentUser = null;
                localStorage.removeItem('userEmail');
                localStorage.removeItem('userId');
                
                // Clear the chat area (flashcards, notes, score, etc.)
                clearChatArea();
                
                // Clear sessions data, chart, and stats
                allSessions = [];
                if (progressChart) {
                    updateProgressChart(allSessions, 5); // Clear the chart
                }
                updateSummaryStats(allSessions); // Reset summary stats
                
                // Disable the app interface
                if (typeof disableAppInterface === 'function') {
                    disableAppInterface();
                }
                
                // Show auth modal and hide topbar
                showAuthModal();
                hideTopBar();
                
                console.log("✅ User logged out successfully - app reset");
            }
        })
        .catch(error => {
            console.error('Logout error:', error);
            // Even if logout fails, reset the UI state
            resetAuthButton();
            showAuthModal();
            hideTopBar();
            
            // Still disable the interface on error
            if (typeof disableAppInterface === 'function') {
                disableAppInterface();
            }
        });
}

// Make sure resetAuthButton function exists and works properly
function resetAuthButton() {
    const submitBtn = document.getElementById('auth-submit');
    if (submitBtn) {
        submitBtn.textContent = 'Continue Studying';
        submitBtn.disabled = false;
    }
}

function showAuthModal() {
    document.getElementById('auth-modal').style.display = 'flex';
    // Pre-fill email if available
    const savedEmail = localStorage.getItem('userEmail');
    if (savedEmail) {
        document.getElementById('auth-email').value = savedEmail;
    }
}

function hideAuthModal() {
    document.getElementById('auth-modal').style.display = 'none';
}

function showTopBar(email) {
    document.getElementById('topbar-email').textContent = email;
    document.getElementById('auth-topbar').style.display = 'block';
    document.body.classList.add('has-topbar');
}

function hideTopBar() {
    const topbar = document.getElementById('auth-topbar');
    if (topbar) {
        topbar.style.display = 'none';
    }
    document.body.classList.remove('has-topbar');
}

function clearUserData() {
    // Will be implemented in later phases
    console.log("User data cleared");
}

// Function to reset UI for new session
function resetUIForNewSession(clearNotes = true) {
    // Clear flashcards
    flashcardsData = [];
    const flashcardsContainer = document.getElementById('flashcards-container');
    flashcardsContainer.innerHTML = `
        <div class="flashcard-placeholder">
            <p>Your studycards will appear here after generating them from your notes.</p>
        </div>
    `;
    
    // Clear notes if requested
    if (clearNotes) {
        document.getElementById('study-notes').value = '';
    }
    
    // Reset score display
    document.getElementById('score-container').textContent = 'Score: 0/0 (0%)';
    
    // Reset save button
    const saveBtn = document.getElementById('save-btn');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Save study session';
    saveBtn.title = 'Generate studycards first';
    hasSavedCurrentSet = false;
    
    // Hide success modal
    hideSuccessModal();
    
    // Reset AI status if exists
    const statusMessage = document.getElementById('ai-status');
    if (statusMessage) {
        statusMessage.textContent = 'AI status: Ready';
        statusMessage.className = 'ai-status';
    }
    
    console.log("✅ UI reset for new session");
}

// Function to just hide the modal and keep everything as-is
function stayInSession() {
    const successModal = document.getElementById('success-modal');
    if (successModal) {
        successModal.style.display = 'none';
    }
    console.log("✅ Staying in current session - all content preserved");
    console.log('Current flashcards:', flashcardsData);
    console.log('Current notes:', document.getElementById('study-notes').value);
    console.log('Score:', document.getElementById('score-container').textContent);
    console.log('Save button state:', document.getElementById('save-btn').textContent);
}

// Function to show success message with options
function showSaveSuccess() {
    const successElement = document.getElementById('save-success');
    successElement.style.display = 'flex';
    
    // Scroll to success message after a brief delay
    setTimeout(() => {
        successElement.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' 
        });
    }, 300);
}

// Function to handle successful save
function handleSaveSuccess() {
    // Update save button state
    const saveBtn = document.getElementById('save-btn');
    saveBtn.disabled = true;
    saveBtn.textContent = '✓ Saved';
    saveBtn.title = 'Session saved! Start a new session to continue.';
    hasSavedCurrentSet = true;
    
    // Show success modal
    showSuccessModal();
    
    // Reload sessions to update progress
    loadSessions();
}

// Helper function to clear flashcards UI only
function clearFlashcardsUI() {
    const flashcardsContainer = document.getElementById('flashcards-container');
    flashcardsContainer.innerHTML = `
        <div class="flashcard-placeholder">
            <p>Session saved! Ready for new studycards.</p>
        </div>
    `;
    
    // Reset score
    document.getElementById('score-container').textContent = 'Score: 0/0 (0%)';
}

// Function to show success modal
function showSuccessModal() {
    const modal = document.getElementById('success-modal');
    modal.style.display = 'flex';
    
    // Add escape key listener
    const escapeHandler = function(e) {
        if (e.key === 'Escape') {
            hideSuccessModal();
            document.removeEventListener('keydown', escapeHandler);
        }
    };
    
    document.addEventListener('keydown', escapeHandler);
}

// Function to hide success modal
function hideSuccessModal() {
    const modal = document.getElementById('success-modal');
    modal.style.display = 'none';
}

// Function to clear the chat/study area
// Function to clear the chat/study area
function clearChatArea() {
    // Clear flashcards
    flashcardsData = [];
    const flashcardsContainer = document.getElementById('flashcards-container');
    if (flashcardsContainer) {
        flashcardsContainer.innerHTML = `
            <div class="flashcard-placeholder">
                <p>Your studycards will appear here after generating them from your notes.</p>
            </div>
        `;
    }
    
    // Clear notes textarea
    const notesTextarea = document.getElementById('study-notes');
    if (notesTextarea) {
        notesTextarea.value = '';
    }
    
    // Reset score display
    const scoreContainer = document.getElementById('score-container');
    if (scoreContainer) {
        scoreContainer.textContent = 'Score: 0/0 (0%)';
    }
    
    // Reset save button to disabled state
    const saveBtn = document.getElementById('save-btn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Save study session';
        saveBtn.title = 'Generate studycards first';
    }
    
    // Reset AI status if exists
    const statusMessage = document.getElementById('ai-status');
    if (statusMessage) {
        statusMessage.textContent = 'AI status: Ready';
        statusMessage.className = 'ai-status';
    }
    
    // Reset session state
    hasSavedCurrentSet = false;
    
    console.log("✅ Chat area cleared");
}

// Function to open the session detail modal
function openSessionModal(sessionId) {
    console.log("Opening modal for session:", sessionId);
    const modal = document.getElementById('session-detail-modal');
    
    // Show loading state
    document.getElementById('session-modal-title').textContent = 'Loading...';
    document.getElementById('session-modal-date').textContent = 'Created: Loading...';
    document.getElementById('session-modal-score').textContent = 'Score: Loading...';
    document.getElementById('session-questions-container').innerHTML = '<div class="question-placeholder">Loading session details...</div>';
    
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    
    // Fetch session data
    fetch(`/get_flashcards/${sessionId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                populateSessionModal(sessionId, data.flashcards);
            } else {
                throw new Error(data.message || 'Failed to load session data');
            }
        })
        .catch(error => {
            console.error('Error fetching session data:', error);
            document.getElementById('session-questions-container').innerHTML = `
                <div class="error-message">
                    <p>Error loading session details: ${error.message}</p>
                    <button onclick="closeSessionModal()" class="modal-btn secondary">Close</button>
                </div>
            `;
        });
}

// Function to close the session detail modal
function closeSessionModal() {
    console.log("Closing session modal");
    const modal = document.getElementById('session-detail-modal');
    modal.style.display = 'none';
    
    // Re-enable background scrolling
    document.body.style.overflow = 'auto';

    // Clear the session ID from delete button (NEW LINE FOR PHASE 4)
    document.getElementById('modal-delete-session-btn').removeAttribute('data-session-id');
}

// Function to populate the modal with session data
function populateSessionModal(sessionId, flashcards) {
    console.log("Populating modal with", flashcards.length, "flashcards");
    
    // Calculate score
    const totalQuestions = flashcards.length;
    const correctAnswers = flashcards.filter(card => card.is_correct).length;
    const scorePercentage = totalQuestions > 0 ? Math.round((correctAnswers / totalQuestions) * 100) : 0;
    
    // Find the session in our loaded sessions to get metadata
    const session = allSessions.find(s => s.id == sessionId);
    
    // Update modal header and metadata
    document.getElementById('session-modal-title').textContent = session ? session.title : `Session ${sessionId}`;
    document.getElementById('session-modal-date').textContent = session ? `Created: ${formatUTCDate(session.created_at)}` : 'Created: Unknown';
    document.getElementById('session-modal-score').textContent = `Score: ${scorePercentage}% (${correctAnswers}/${totalQuestions})`;
    
    // Generate questions HTML
    const questionsHTML = generateQuestionsHTML(flashcards);
    document.getElementById('session-questions-container').innerHTML = questionsHTML;
    
    // Store the session ID on the delete button
    const deleteBtn = document.getElementById('modal-delete-session-btn');
    deleteBtn.setAttribute('data-session-id', sessionId);
    
    // Ensure delete button is reset to normal state
    deleteBtn.textContent = 'Delete Session';
    deleteBtn.disabled = false;
}

// Function to generate HTML for all questions in a session
function generateQuestionsHTML(flashcards) {
    if (!flashcards || flashcards.length === 0) {
        return '<div class="no-questions-message">No questions found in this session.</div>';
    }
    
    return flashcards.map((card, index) => {
        const userAnswer = card.user_answer;
        const correctAnswer = card.correct_answer;
        const isCorrect = userAnswer === correctAnswer;
        
        return `
            <div class="session-question">
                <div class="session-question-text">${index + 1}. ${card.question}</div>
                <div class="session-options">
                    ${card.options.map((option, optIndex) => {
                        const isUserAnswer = optIndex === userAnswer;
                        const isCorrectAnswer = optIndex === correctAnswer;
                        
                        let optionClass = 'session-option';
                        if (isUserAnswer) optionClass += isCorrect ? ' correct' : ' incorrect';
                        if (isCorrectAnswer && !isUserAnswer) optionClass += ' correct';
                        
                        let indicator = '';
                        if (isUserAnswer) indicator = isCorrect ? ' ✓ Your answer' : ' ✗ Your answer';
                        if (isCorrectAnswer && !isUserAnswer) indicator = ' ✓ Correct answer';
                        
                        return `
                            <div class="${optionClass}">
                                ${String.fromCharCode(65 + optIndex)}) ${option}
                                ${indicator ? `<span class="answer-indicator">${indicator}</span>` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }).join('');
}

// Function to delete a session from the modal
function deleteSessionFromModal(sessionId) {
    console.log("Deleting session from modal:", sessionId);
    
    // Show loading state on the delete button
    const deleteBtn = document.getElementById('modal-delete-session-btn');
    const originalText = deleteBtn.textContent;
    deleteBtn.textContent = 'Deleting...';
    deleteBtn.disabled = true;
    
    fetch(`/delete_session/${sessionId}`, { 
        method: 'DELETE' 
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Close the modal first
            closeSessionModal();
            
            // Then reload sessions to update the list
            loadSessions(currentPage);
            
            // Show a brief success message (optional)
            showTempMessage("Session deleted successfully", "success");
        } else {
            throw new Error(data.message || 'Failed to delete session');
        }
    })
    .catch(error => {
        console.error('Error deleting session:', error);
        alert('Error deleting session: ' + error.message);
        
        // Restore button state on error
        deleteBtn.textContent = originalText;
        deleteBtn.disabled = false;
    });
}

// Helper function to show temporary messages
function showTempMessage(message, type = 'success') {
    // Create message element
    const messageEl = document.createElement('div');
    messageEl.className = `temp-message temp-message-${type}`;
    messageEl.textContent = message;
    
    // Add to page
    document.body.appendChild(messageEl);
    
    // Remove after animation
    setTimeout(() => {
        if (messageEl.parentNode) {
            messageEl.parentNode.removeChild(messageEl);
        }
    }, 2800);
}

// Helper function to format dates to UTC
function formatUTCDate(dateString) {
    const date = new Date(dateString);
    // Format as: YYYY-MM-DD at HH:MM
    return `${
        date.getUTCFullYear()
    }-${
        String(date.getUTCMonth() + 1).padStart(2, '0')
    }-${
        String(date.getUTCDate()).padStart(2, '0')
    } at ${
        String(date.getUTCHours()).padStart(2, '0')
    }:${
        String(date.getUTCMinutes()).padStart(2, '0')
    }`;
}

// Function to handle logo click and refresh page
function setupLogoRefresh() {
    const logo = document.getElementById('logo');
    
    if (logo) {
        logo.addEventListener('click', function() {           
            window.location.reload();
        });
    }
}

// Function to fetch and update tier information
async function updateTierInfo() {
    try {
        const response = await fetch('/user/tier-info');
        const data = await response.json();
        
        if (data.status === 'success') {
            const tierInfo = data.tier_info;
            
            // Update tier graphic (both desktop and mobile)
            const tierElement = document.getElementById('user-tier');
            const mobileTierElement = document.getElementById('mobile-user-tier');
            
            if (tierElement) {
                tierElement.textContent = tierInfo.tier.charAt(0).toUpperCase() + tierInfo.tier.slice(1) + ' Plan';
                tierElement.className = `tier-graphic ${tierInfo.tier}-tier`;
            }
            
            if (mobileTierElement) {
                mobileTierElement.textContent = tierInfo.tier.charAt(0).toUpperCase() + tierInfo.tier.slice(1) + ' Plan';
                mobileTierElement.className = `tier-graphic ${tierInfo.tier}-tier`;
            }
            
            // Update sessions remaining (both)
            const sessionsElement = document.getElementById('sessions-remaining');
            const mobileSessionsElement = document.getElementById('mobile-sessions-remaining');
            
            if (sessionsElement) {
                sessionsElement.textContent = `Sessions remaining: ${tierInfo.remaining_sessions}`;
            }
            if (mobileSessionsElement) {
                mobileSessionsElement.textContent = `Sessions remaining: ${tierInfo.remaining_sessions}`;
            }
            
            // Update reset time (both)
            const resetElement = document.getElementById('resets-in');
            const mobileResetElement = document.getElementById('mobile-resets-in');
            
            if (resetElement) {
                resetElement.textContent = `Resets in: ${tierInfo.reset_in}`;
            }
            if (mobileResetElement) {
                mobileResetElement.textContent = `Resets in: ${tierInfo.reset_in}`;
            }
        } else {
            console.error('Failed to fetch tier info:', data.message);
            // Fallback for both desktop and mobile
            const fallbackText = 'Free Plan';
            document.querySelectorAll('.tier-graphic').forEach(el => {
                el.textContent = fallbackText;
            });
            document.querySelectorAll('.sessions-remaining').forEach(el => {
                el.textContent = 'Sessions remaining: 3';
            });
            document.querySelectorAll('.resets-in').forEach(el => {
                el.textContent = 'Resets in: 24h 0m';
            });
        }
    } catch (error) {
        console.error('Error fetching tier info:', error);
        // Fallback for both on error
        const fallbackText = 'Free Plan';
        document.querySelectorAll('.tier-graphic').forEach(el => {
            el.textContent = fallbackText;
        });
        document.querySelectorAll('.sessions-remaining').forEach(el => {
            el.textContent = 'Sessions remaining: 3';
        });
        document.querySelectorAll('.resets-in').forEach(el => {
            el.textContent = 'Resets in: 24h 0m';
        });
    }
}

// Function to navigate To Upgrade when upgrade btn is clicked
function navigateToUpgrade() {
    window.location.href = '/upgrade';
}

// Add this function to your script.js
function disableAppInterface() {
    // Disable generate button
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) generateBtn.disabled = true;
    
    // Disable save button
    const saveBtn = document.getElementById('save-btn');
    if (saveBtn) saveBtn.disabled = true;
    
    // Clear any existing studycards
    flashcardsData = [];
    const flashcardsContainer = document.getElementById('flashcards-container');
    if (flashcardsContainer) {
        flashcardsContainer.innerHTML = `
            <div class="flashcard-placeholder">
                <p>Please sign in to generate studycards</p>
            </div>
        `;
    }
    
    // Reset score display
    const scoreContainer = document.getElementById('score-container');
    if (scoreContainer) scoreContainer.textContent = 'Score: 0/0 (0%)';
    
    // Clear notes
    const notesTextarea = document.getElementById('study-notes');
    if (notesTextarea) notesTextarea.value = '';
    
    // Clear sessions
    const sessionsContainer = document.getElementById('sessions-container');
    if (sessionsContainer) sessionsContainer.innerHTML = '<p class="no-sessions">Please sign in to view your study sessions</p>';
    
    // Clear chart
    if (progressChart) {
        progressChart.data.labels = [];
        progressChart.data.datasets[0].data = [];
        progressChart.data.datasets[1].data = [];
        progressChart.update();
    }
    
    // Reset stats
    updateSummaryStats([]);
}

function enableAppInterface() {
    // Enable generate button
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) generateBtn.disabled = false;
    
    // Update save button state based on current conditions
    updateSaveButtonState();
    
    // Reset any placeholder messages
    const flashcardsContainer = document.getElementById('flashcards-container');
    if (flashcardsContainer && flashcardsData.length === 0) {
        flashcardsContainer.innerHTML = `
            <div class="flashcard-placeholder">
                <p>Your studycards will appear here after generating them from your notes.</p>
            </div>
        `;
    }
}

// Mobile Menu Functions
function initMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileMenu = document.getElementById('mobile-menu');
    
    if (!mobileMenuToggle || !mobileMenu) {
        console.log('Mobile menu elements not found');
        return false;
    }
    
    // Toggle mobile menu
    mobileMenuToggle.addEventListener('click', function(e) {
        e.stopPropagation();
        this.classList.toggle('active');
        mobileMenu.classList.toggle('active');
        document.body.style.overflow = mobileMenu.classList.contains('active') ? 'hidden' : '';
    });
    
    // Close menu when clicking outside
    document.addEventListener('click', function(event) {
        if (mobileMenu.classList.contains('active') && 
            !mobileMenu.contains(event.target) && 
            !mobileMenuToggle.contains(event.target)) {
            closeMobileMenu();
        }
    });
    
    // Close menu on escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && mobileMenu.classList.contains('active')) {
            closeMobileMenu();
        }
    });
    
    function closeMobileMenu() {
        mobileMenuToggle.classList.remove('active');
        mobileMenu.classList.remove('active');
        document.body.style.overflow = '';
    }
    
    // Close menu when clicking on menu items
    const menuItems = mobileMenu.querySelectorAll('button, a');
    menuItems.forEach(item => {
        item.addEventListener('click', closeMobileMenu);
    });
    
    console.log('Mobile menu initialized successfully');
    return true;
}

// Function to sync data between desktop and mobile elements
function syncMobileDesktopData() {
    // Sync tier information
    const desktopTier = document.getElementById('user-tier');
    const mobileTier = document.getElementById('mobile-user-tier');
    if (desktopTier && mobileTier) {
        mobileTier.textContent = desktopTier.textContent;
        mobileTier.className = desktopTier.className;
    }
    
    // Sync sessions remaining
    const desktopSessions = document.getElementById('sessions-remaining');
    const mobileSessions = document.getElementById('mobile-sessions-remaining');
    if (desktopSessions && mobileSessions) {
        mobileSessions.textContent = desktopSessions.textContent;
    }
    
    // Sync reset time
    const desktopReset = document.getElementById('resets-in');
    const mobileReset = document.getElementById('mobile-resets-in');
    if (desktopReset && mobileReset) {
        mobileReset.textContent = desktopReset.textContent;
    }
    
    // Sync email
    const desktopEmail = document.getElementById('topbar-email');
    const mobileEmail = document.getElementById('mobile-topbar-email');
    if (desktopEmail && mobileEmail) {
        mobileEmail.textContent = desktopEmail.textContent;
    }
}