const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/index.js'), 'utf8');

function setup() {
    const list = {innerHTML: '既存の依頼', dataset: {refreshUrl: '/posts/list'}, contains: () => false};
    const status = {};
    const handlers = {};
    let refresh, responseHtml = '新しい依頼', failed = false, calls = 0;
    const document = {
        hidden: false,
        getElementById: id => id === 'posts-list' ? list : status,
        createElement: () => ({innerHTML: ''}),
        addEventListener: (event, fn) => handlers[event] = fn,
    };
    const context = vm.createContext({
        document,
        setInterval(fn, interval) {assert.equal(interval, 3000); refresh = fn;},
        fetch: async (url, options) => {
            calls++;
            assert.equal(url, list.dataset.refreshUrl);
            assert.equal(options.cache, 'no-store');
            return {ok: !failed, redirected: false, text: async () => responseHtml};
        },
    });
    vm.runInContext(source, context);
    return {list, status, document, handlers,
        refresh: () => refresh(),
        fail() {failed = true;}, recover() {failed = false;},
        get calls() {return calls;},
    };
}

test('new posts appear automatically and hidden tabs pause polling', async () => {
    const app = setup();
    await app.refresh();
    assert.equal(app.list.innerHTML, '新しい依頼');
    app.document.hidden = true;
    await app.refresh();
    assert.equal(app.calls, 1);
    app.document.hidden = false;
    app.handlers.visibilitychange();
    await new Promise(setImmediate);
    assert.equal(app.calls, 2);
});

test('failed refresh preserves list and retries successfully', async () => {
    const app = setup();
    app.fail();
    await app.refresh();
    assert.equal(app.list.innerHTML, '既存の依頼');
    assert.match(app.status.textContent, /再接続/);
    app.recover();
    await app.refresh();
    assert.equal(app.list.innerHTML, '新しい依頼');
});

test('overlapping refresh requests are suppressed', async () => {
    const app = setup();
    await Promise.all([app.refresh(), app.refresh()]);
    assert.equal(app.calls, 1);
});

test('keyboard focus stays on the same post link after replacement', async () => {
    const app = setup();
    let focused = false;
    app.document.activeElement = {getAttribute: () => '/post/1'};
    app.list.contains = () => true;
    app.list.querySelectorAll = () => [{getAttribute: () => '/post/1', focus(options) {focused = options.preventScroll;}}];
    await app.refresh();
    assert.equal(focused, true);
});

test('selected status is included in every automatic refresh', async () => {
    const app = setup();
    app.list.dataset.refreshUrl = '/posts/list?status=discussing';
    await app.refresh();
    await app.refresh();
    assert.equal(app.calls, 2);
    assert.equal(app.list.dataset.refreshUrl, '/posts/list?status=discussing');
});


test('owner and status selection stay in the automatic refresh URL', async () => {
    const app = setup();
    app.list.dataset.refreshUrl = '/posts/list?status=discussing&owner=mine';
    await app.refresh();
    await app.refresh();
    assert.equal(app.calls, 2);
    assert.equal(app.list.dataset.refreshUrl, '/posts/list?status=discussing&owner=mine');
});
