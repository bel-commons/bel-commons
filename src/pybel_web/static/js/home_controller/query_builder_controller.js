/**
 * This JS file controls the QueryBuilder forms as well as autocompletions in query_builder.html
 *
 * @summary   QueryBuilder of PyBEL explorer
 *
 * @requires jquery, select2
 *
 */


// Controls that at least a network has been selected
$('#query-form').on('submit', function (e) {
    if ($("input[type=checkbox]:checked").length === 0) {
        e.preventDefault();
        alert('Please select at least one network in your query.');
        return false;
    }
});


$(document).ready(function () {

    // Autocompletion for author seeding
    $("#author_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type any authors",
        ajax: {
            url: function () {
                return "/api/author/suggestion/";
            },
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.text,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });

    // Autocompletion for pubmeds seeding
    $("#pubmed_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type PubMed identifiers",
        ajax: {
            url: function () {
                return "/api/citation/pubmed/suggestion/";
            },
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.text,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });

    // Autocompletion for annotation seeding
    $("#annotation_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type any annotation",
        ajax: {
            url: function () {
                return "/api/annotation/suggestion/";
            },
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.annotation + ':' + item.value,  // 'Annotation:value'
                                text: item.annotation + ':' + item.value  //'Annotation:value'
                            };
                        }
                    )
                };
            }
        }
    });

    // Autocompletion for nodes seeding
    $("#node_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: 'Please type any node',
        ajax: {
            url: "/api/node/suggestion/",
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.id, // node_id
                                text: item.text // bel
                            };
                        }
                    )
                };
            }
        }
    });

    // Autocompletion in the first input
    $('#pipeline').autocomplete({
        source: function (request, response) {
            $.ajax({
                url: "/api/pipeline/suggestion/",
                dataType: "json",
                data: {
                    term: request.term
                },
                success: function (data) {
                    response(data); // functionName
                }
            });
        }, minLength: 2
    });


});


/**
 * * Dynamically adds/deletes pipeline inputs
 */
$(function () {
    // Remove button click
    $(document).on(
        'click',
        '[data-role="dynamic-fields"] > .form-inline [data-role="remove"]',
        function (e) {
            e.preventDefault();
            $(this).closest('.form-inline').remove();
        }
    );
    // Add button click
    $(document).on(
        'click',
        '[data-role="dynamic-fields"] > .form-inline [data-role="add"]',
        function (e) {
            e.preventDefault();
            var container = $(this).closest('[data-role="dynamic-fields"]');
            var new_field_group = container.children().filter('.form-inline:first-child').clone();
            new_field_group.find('input').each(function () {
                $(this).val(''); // Empty current value and start autocompletion
                $(this).autocomplete({
                    source: function (request, response) {
                        $.ajax({
                            url: "/api/pipeline/suggestion/",
                            dataType: "json",
                            data: {
                                term: request.term
                            },
                            success: function (data) {
                                response(data);
                            }
                        });
                    }, minLength: 2
                });
            });
            container.append(new_field_group);
        }
    );
});





