const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/js/detail.js'), 'utf8');

function screen(state, viewer = 'helper') {
    const nodes = {};
    function node(id, props) {
        const element = {
            ...props,
            replaceWith(next) { nodes[id] = next; next.replaceWith = this.replaceWith; next.remove = this.remove; },
            remove() { delete nodes[id]; },
        };
        nodes[id] = element;
    }
    node('chatLogs', {innerHTML: '会話', scrollHeight: 100, scrollTop: 0});
    node('confirmation-notification', {hidden: true});
    node('completion-notification', {hidden: true});
    if (state) node('request-status', {dataset: {state, viewer}, outerHTML: state + viewer});
    node('contact-details', {innerHTML: state === 'confirmed' ? '公開された連絡先' : '非公開'});
    return {nodes, title: '案件詳細', getElementById(id) { return nodes[id] || null; }, addEventListener() {}};
}

function setup(initialState = 'pending', viewer = 'helper') {
    const document = screen(initialState, viewer);
    let incoming = screen('confirmed', viewer);
    let refresh;
    let fetchCount = 0;
    let responseOk = true;
    vm.runInNewContext(source, {
        document,
        window: {location: {href: 'http://localhost/post/1'}},
        setInterval(fn, ms) { assert.equal(ms, 3000); refresh = fn; },
        fetch: async () => {
            fetchCount++;
            return {ok: responseOk, redirected: false, text: async () => ''};
        },
        DOMParser: class { parseFromString() { return incoming; } },
        console: {log() {}},
    });
    return {
        document,
        async refresh() { refresh(); await new Promise(setImmediate); },
        setIncoming(doc) { incoming = doc; },
        failResponse() { responseOk = false; },
        get fetchCount() { return fetchCount; },
    };
}

test('confirmation appears without reloading or replacing the chat input', async () => {
    const app = setup();
    const input = {value: '入力途中のメッセージ'};
    app.document.nodes.input = input;
    await app.refresh();
    assert.equal(app.document.nodes['request-status'].dataset.state, 'confirmed');
    assert.equal(app.document.nodes['contact-details'].innerHTML, '公開された連絡先');
    assert.equal(app.document.nodes['confirmation-notification'].hidden, false);
    assert.equal(app.document.title, '【依頼確定】案件詳細');
    assert.equal(app.document.nodes.input, input);
    assert.equal(input.value, '入力途中のメッセージ');
    await app.refresh();
    assert.equal(app.document.title, '【依頼確定】案件詳細');
});

test('owner does not receive the helper notification', async () => {
    const app = setup('pending', 'author');
    await app.refresh();
    assert.equal(app.document.nodes['confirmation-notification'].hidden, true);
    assert.equal(app.document.title, '案件詳細');
});

test('already confirmed page does not create a new notification on every poll', async () => {
    const app = setup('confirmed');
    await app.refresh();
    assert.equal(app.document.nodes['confirmation-notification'].hidden, true);
});

test('cancellation clears the notification and private contact display', async () => {
    const app = setup();
    await app.refresh();
    app.setIncoming(screen(null));
    await app.refresh();
    assert.equal(app.document.nodes['request-status'], undefined);
    assert.equal(app.document.nodes['confirmation-notification'].hidden, true);
    assert.equal(app.document.nodes['contact-details'].innerHTML, '非公開');
    assert.equal(app.document.title, '案件詳細');
});

test('failed fetch preserves the page and allows a retry', async () => {
    const app = setup();
    app.failResponse();
    await app.refresh();
    await app.refresh();
    assert.equal(app.fetchCount, 2);
    assert.equal(app.document.nodes['request-status'].dataset.state, 'pending');
    assert.equal(app.document.nodes['confirmation-notification'].hidden, true);
});

test('helper sees live completion notification and updated status', async () => {
    const app = setup('confirmed');
    app.setIncoming(screen('completed'));
    await app.refresh();
    assert.equal(app.document.nodes['request-status'].dataset.state, 'completed');
    assert.equal(app.document.nodes['completion-notification'].hidden, false);
    assert.equal(app.document.nodes['confirmation-notification'].hidden, true);
    assert.equal(app.document.title, '【依頼終了】案件詳細');
    await app.refresh();
    assert.equal(app.document.title, '【依頼終了】案件詳細');
});
