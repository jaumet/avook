/*!
 * Start Bootstrap - Freelancer Bootstrap Theme (http://startbootstrap.com)
 * Code licensed under the Apache License v2.0.
 * For details, see http://www.apache.org/licenses/LICENSE-2.0.
 */

// jQuery for page scrolling feature - requires jQuery Easing plugin
$(function() {
    // Initial setup check
    if (window.location.pathname.indexOf('setup/create-superuser') === -1) {
        fetch('/api/v1/admin/setup-status')
            .then(function(response) {
                if (response.ok) {
                    return response.json();
                } else {
                    // If the API is down or there's an error, we don't redirect.
                    console.error('Setup status check failed.');
                }
            })
            .then(function(data) {
                if (data && data.superuser_exists === false) {
                    // No superuser exists, redirect to the setup page.
                    // We assume the setup page is at the root for now.
                    window.location.href = '/setup/create-superuser.html';
                }
            })
            .catch(function(error) {
                console.error('Error during setup status check:', error);
            });
    }


    $('.page-scroll a').bind('click', function(event) {
        var $anchor = $(this);
        $('html, body').stop().animate({
            scrollTop: $($anchor.attr('href')).offset().top
        }, 1500, 'easeInOutExpo');
        event.preventDefault();
    });

    // Admin link visibility check
    var token = localStorage.getItem('token');
    if (token) {
        fetch('/api/v1/admin/users/ping', {
            headers: {
                'Authorization': 'Bearer ' + token
            }
        })
        .then(function(response) {
            if (response.ok) {
                $('#admin-nav-link').show();
            }
        })
        .catch(function(error) {
            // Do nothing, link remains hidden
            console.error('Could not verify superuser status for nav link.', error);
        });
    }
});

// Floating label headings for the contact form
$(function() {
    $("body").on("input propertychange", ".floating-label-form-group", function(e) {
        $(this).toggleClass("floating-label-form-group-with-value", !! $(e.target).val());
    }).on("focus", ".floating-label-form-group", function() {
        $(this).addClass("floating-label-form-group-with-focus");
    }).on("blur", ".floating-label-form-group", function() {
        $(this).removeClass("floating-label-form-group-with-focus");
    });
});

// Highlight the top nav as scrolling occurs
$('body').scrollspy({
    target: '.navbar-fixed-top'
})

// Closes the Responsive Menu on Menu Item Click
$('.navbar-collapse ul li a').click(function() {
    $('.navbar-toggle:visible').click();
});
