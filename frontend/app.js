// ==================== グローバル変数 ====================
let currentPage = 'home';
let chatHistories = {
    'daily': [],
    'ai': [],
    'teacher': []
};

// ==================== DOM要素の取得 ====================
const elements = {
    // ナビゲーション関連
    hamburgerBtn: document.getElementById('hamburgerBtn'),
    sideNav: document.getElementById('sideNav'),
    closeNav: document.getElementById('closeNav'),
    navOverlay: document.getElementById('navOverlay'),
    appTitle: document.getElementById('appTitle'),
    navItems: document.querySelectorAll('.nav-item'),
    
    // ページ関連
    pages: {
        'home': document.getElementById('homePage'),
        'daily-chat': document.getElementById('dailyChatPage'),
        'ai-chat': document.getElementById('aiChatPage'),
        'teacher-chat': document.getElementById('teacherChatPage'),
        'recommend': document.getElementById('recommendPage')
    },
    
    // フィーチャーカード
    featureCards: document.querySelectorAll('.feature-card'),
    
    // チャット関連
    chatData: {
        'daily': {
            input: document.getElementById('dailyChatInput'),
            messages: document.getElementById('dailyChatMessages'),
            sendBtn: document.querySelector('[data-chat="daily"]')
        },
        'ai': {
            input: document.getElementById('aiChatInput'),
            messages: document.getElementById('aiChatMessages'),
            sendBtn: document.querySelector('[data-chat="ai"]')
        },
        'teacher': {
            input: document.getElementById('teacherChatInput'),
            messages: document.getElementById('teacherChatMessages'),
            sendBtn: document.querySelector('[data-chat="teacher"]')
        }
    },
    
    // レコメンドカード
    recommendCards: document.querySelectorAll('.recommend-card')
};

// ==================== ナビゲーション制御 ====================
class NavigationController {
    constructor() {
        this.initEventListeners();
    }
    
    initEventListeners() {
        // ハンバーガーボタンクリック
        elements.hamburgerBtn.addEventListener('click', () => this.openSideNav());
        
        // ナビゲーションを閉じる
        elements.closeNav.addEventListener('click', () => this.closeSideNav());
        elements.navOverlay.addEventListener('click', () => this.closeSideNav());
        
        // ESCキーでナビゲーションを閉じる
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && elements.sideNav.classList.contains('active')) {
                this.closeSideNav();
            }
        });
    }
    
    openSideNav() {
        elements.sideNav.classList.add('active');
        elements.hamburgerBtn.classList.add('active');
        document.body.style.overflow = 'hidden'; // スクロールを無効化
    }
    
    closeSideNav() {
        elements.sideNav.classList.remove('active');
        elements.hamburgerBtn.classList.remove('active');
        document.body.style.overflow = ''; // スクロールを復活
    }
}

// ==================== ページ管理 ====================
class PageManager {
    constructor() {
        this.initEventListeners();
    }
    
    initEventListeners() {
        // タイトルクリックでホームへ
        elements.appTitle.addEventListener('click', () => this.switchPage('home'));
        
        // ナビゲーションアイテムのクリック
        elements.navItems.forEach(item => {
            item.addEventListener('click', () => {
                const page = item.getAttribute('data-page');
                this.switchPage(page);
            });
        });
        
        // フィーチャーカードのクリック
        elements.featureCards.forEach(card => {
            card.addEventListener('click', () => {
                const page = card.getAttribute('data-page');
                this.switchPage(page);
            });
        });
    }
    
    switchPage(pageName) {
        // 全ページを非表示
        Object.values(elements.pages).forEach(page => {
            if (page) page.classList.remove('active');
        });
        
        // 選択されたページを表示
        if (elements.pages[pageName]) {
            elements.pages[pageName].classList.add('active');
            currentPage = pageName;
            
            // ページ履歴を更新（ブラウザの戻るボタン対応）
            history.pushState({ page: pageName }, '', `#${pageName}`);
        }
        
        // ナビゲーションを閉じる
        navigation.closeSideNav();
        
        // ページ切り替え時のアニメーション
        this.animatePageTransition(pageName);
    }
    
    animatePageTransition(pageName) {
        const page = elements.pages[pageName];
        if (page) {
            page.style.opacity = '0';
            setTimeout(() => {
                page.style.opacity = '1';
            }, 50);
        }
    }
}

// ==================== チャット機能 ====================
class ChatManager {
    constructor() {
        this.botResponses = {
            'daily': [
                '興味深いお話ですね！もっと詳しく聞かせてください。',
                'そうなんですね。それについてどう感じましたか？',
                'なるほど！それは素敵ですね。',
                '今日も一日お疲れさまでした。',
                'それは大変でしたね。でも頑張りましたね！'
            ],
            'ai': [
                'なるほど、それについてもう少し考えてみましょう。',
                'ご質問ありがとうございます。私の理解では...',
                'それは興味深い観点ですね。',
                '他に何かお手伝いできることはありますか？',
                'その件について、こう考えてみてはいかがでしょうか。'
            ],
            'teacher': [
                'ご相談ありがとうございます。一緒に考えていきましょう。',
                'それは重要なポイントですね。',
                '君の考えを聞かせてください。',
                'いい質問ですね。段階的に考えてみましょう。',
                'その努力は素晴らしいですよ。'
            ]
        };
        
        this.initEventListeners();
        this.loadChatHistories();
    }
    
    initEventListeners() {
        // 送信ボタンのクリックイベント
        Object.keys(elements.chatData).forEach(chatType => {
            const chat = elements.chatData[chatType];
            
            // 送信ボタンクリック
            chat.sendBtn.addEventListener('click', () => {
                this.sendMessage(chatType);
            });
            
            // Enterキーで送信
            chat.input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage(chatType);
                }
            });
            
            // Shift+Enterで改行
            chat.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && e.shiftKey) {
                    // デフォルトの動作（改行）を許可
                }
            });
        });
    }
    
    sendMessage(chatType) {
        const chat = elements.chatData[chatType];
        if (!chat) return;
        
        const messageText = chat.input.value.trim();
        if (messageText === '') return;
        
        // ユーザーメッセージを追加
        this.addMessage(chatType, messageText, 'user');
        
        // 入力欄をクリア
        chat.input.value = '';
        
        // タイピングインジケーターを表示
        this.showTypingIndicator(chatType);
        
        // ボットの返信をシミュレート
        setTimeout(() => {
            this.removeTypingIndicator(chatType);
            const responses = this.botResponses[chatType];
            const randomResponse = responses[Math.floor(Math.random() * responses.length)];
            this.addMessage(chatType, randomResponse, 'bot');
        }, 1000 + Math.random() * 1000);
    }
    
    addMessage(chatType, text, sender) {
        const chat = elements.chatData[chatType];
        if (!chat) return;
        
        // メッセージ要素を作成
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = text;
        
        messageDiv.appendChild(messageContent);
        chat.messages.appendChild(messageDiv);
        
        // チャット履歴に保存
        chatHistories[chatType].push({
            sender: sender,
            text: text,
            timestamp: new Date().toISOString()
        });
        
        // ローカルストレージに保存
        this.saveChatHistory(chatType);
        
        // スクロールを下へ
        this.scrollToBottom(chat.messages);
    }
    
    showTypingIndicator(chatType) {
        const chat = elements.chatData[chatType];
        if (!chat) return;
        
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot-message typing-indicator';
        typingDiv.innerHTML = `
            <div class="message-content">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        
        chat.messages.appendChild(typingDiv);
        this.scrollToBottom(chat.messages);
    }
    
    removeTypingIndicator(chatType) {
        const chat = elements.chatData[chatType];
        if (!chat) return;
        
        const typingIndicator = chat.messages.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
    
    scrollToBottom(element) {
        element.scrollTop = element.scrollHeight;
        
        // スムーズスクロール
        element.scrollTo({
            top: element.scrollHeight,
            behavior: 'smooth'
        });
    }
    
    saveChatHistory(chatType) {
        try {
            localStorage.setItem(`chat_${chatType}`, JSON.stringify(chatHistories[chatType]));
        } catch (e) {
            console.log('ローカルストレージへの保存に失敗しました:', e);
        }
    }
    
    loadChatHistories() {
        Object.keys(chatHistories).forEach(chatType => {
            try {
                const saved = localStorage.getItem(`chat_${chatType}`);
                if (saved) {
                    const history = JSON.parse(saved);
                    chatHistories[chatType] = history;
                    
                    // 履歴をUIに反映
                    history.forEach(msg => {
                        this.displayHistoryMessage(chatType, msg);
                    });
                }
            } catch (e) {
                console.log('チャット履歴の読み込みに失敗しました:', e);
            }
        });
    }
    
    displayHistoryMessage(chatType, msg) {
        const chat = elements.chatData[chatType];
        if (!chat) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.sender}-message`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = msg.text;
        
        messageDiv.appendChild(messageContent);
        
        // 初期メッセージの後に履歴を挿入
        const firstBotMessage = chat.messages.querySelector('.bot-message');
        if (firstBotMessage && firstBotMessage.nextSibling) {
            chat.messages.insertBefore(messageDiv, firstBotMessage.nextSibling);
        } else {
            chat.messages.appendChild(messageDiv);
        }
    }
    
    clearChatHistory(chatType) {
        chatHistories[chatType] = [];
        localStorage.removeItem(`chat_${chatType}`);
        
        const chat = elements.chatData[chatType];
        if (chat) {
            // 初期メッセージ以外を削除
            const messages = chat.messages.querySelectorAll('.message:not(:first-child)');
            messages.forEach(msg => msg.remove());
        }
    }
}

// ==================== レコメンド機能 ====================
class RecommendManager {
    constructor() {
        this.initEventListeners();
    }
    
    initEventListeners() {
        elements.recommendCards.forEach(card => {
            card.addEventListener('click', () => {
                this.handleRecommendClick(card);
            });
        });
    }
    
    handleRecommendClick(card) {
        const title = card.querySelector('h3').textContent;
        
        // クリックフィードバック
        card.style.transform = 'scale(0.95)';
        setTimeout(() => {
            card.style.transform = '';
        }, 200);
        
        // アラート表示（実際のアプリでは詳細画面に遷移）
        this.showRecommendDetail(title);
    }
    
    showRecommendDetail(title) {
        // モーダルやアラートで詳細を表示
        alert(`「${title}」の詳細を表示します。\n\n実際のアプリケーションでは、ここで詳細画面に遷移します。`);
    }
}

// ==================== ユーティリティ関数 ====================
class Utils {
    static formatDate(date) {
        const options = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        };
        return new Date(date).toLocaleDateString('ja-JP', options);
    }
    
    static debounce(func, wait) {
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
    
    static isMobile() {
        return window.innerWidth <= 768;
    }
}

// ==================== タイピングインジケーターCSS ====================
const style = document.createElement('style');
style.textContent = `
    .typing-indicator .message-content {
        display: flex;
        align-items: center;
        padding: 1rem;
    }
    
    .typing-indicator span {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #666;
        margin: 0 2px;
        animation: typing 1.4s infinite;
    }
    
    .typing-indicator span:nth-child(1) {
        animation-delay: 0s;
    }
    
    .typing-indicator span:nth-child(2) {
        animation-delay: 0.2s;
    }
    
    .typing-indicator span:nth-child(3) {
        animation-delay: 0.4s;
    }
    
    @keyframes typing {
        0%, 60%, 100% {
            transform: translateY(0);
            opacity: 0.5;
        }
        30% {
            transform: translateY(-10px);
            opacity: 1;
        }
    }
`;
document.head.appendChild(style);

// ==================== アプリケーション初期化 ====================
class App {
    constructor() {
        this.navigation = new NavigationController();
        this.pageManager = new PageManager();
        this.chatManager = new ChatManager();
        this.recommendManager = new RecommendManager();
        
        this.init();
    }
    
    init() {
        // URLハッシュによる初期ページ設定
        this.handleInitialRoute();
        
        // ブラウザの戻る/進むボタン対応
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.page) {
                this.pageManager.switchPage(e.state.page);
            }
        });
        
        // ウィンドウリサイズ対応
        window.addEventListener('resize', Utils.debounce(() => {
            this.handleResize();
        }, 250));
        
        console.log('TEST APP initialized successfully!');
    }
    
    handleInitialRoute() {
        const hash = window.location.hash.replace('#', '');
        if (hash && elements.pages[hash]) {
            this.pageManager.switchPage(hash);
        } else {
            this.pageManager.switchPage('home');
        }
    }
    
    handleResize() {
        // モバイル/デスクトップ切り替え時の処理
        if (Utils.isMobile()) {
            // モバイル用の調整
            document.body.classList.add('mobile');
        } else {
            // デスクトップ用の調整
            document.body.classList.remove('mobile');
        }
    }
}

// ==================== アプリケーション起動 ====================
let app;
let navigation;

document.addEventListener('DOMContentLoaded', () => {
    navigation = new NavigationController();
    app = new App();
});

// ==================== Service Worker登録（PWA対応） ====================
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').then(
            registration => console.log('ServiceWorker registration successful'),
            err => console.log('ServiceWorker registration failed: ', err)
        );
    });
}