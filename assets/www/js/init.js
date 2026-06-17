'use strict';

function init() {
	window.APPLICATION_NAME_DISPLAY = 'Dofus Touch';

	// to replace build's alert title "index.html"
	window.alert = function (msg) {
		window.navigator.notification.alert(msg, null, window.APPLICATION_NAME_DISPLAY, 'Ok');
	};
}
init();
