// ログイン画面を開いたときも、最初から入力欄にカーソルを合わせる
window.addEventListener('DOMContentLoaded', function () {
  const loginField = document.getElementById('loginIdField');
  if (loginField) {
    loginField.focus();
  }
});
