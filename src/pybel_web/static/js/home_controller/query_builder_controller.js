/**
 * This JS file controls the QueryBuilder forms as well as autocompletions in query_builder.html
 *
 * @summary   QueryBuilder of PyBEL explorer
 *
 * @requires jquery, select2
 *
 */

/**
 * Returns array with the properties of selection in a select2Element.
 * @param {object} parameters object
 * @param {string} key of the parameter
 * @param {select2} select2Element
 * @param {string} selectionProperty - text or id
 */
function addQueryParameters(parameters, key, select2Element, selectionProperty) {

    var selectedElements = [];

    $.each(select2Element, function (index, value) {
        selectedElements.push(encodeURIComponent(value[selectionProperty]));
    });

    if (!($.isEmptyObject(selectedElements))) {
        parameters[key] = selectedElements;
    }
}

/**
 * Adds checkbox parameter
 * @param {object} parameters object
 * @param {string} key
 */
function addPipelineParameters(parameters, key) {

    var pipeline = [];
    $("input[name=pipeline]").each(function () {

        var value = $(this).val();

        if (value) {
            pipeline.push(value);
        }
    });

    if (!($.isEmptyObject(pipeline))) {
        parameters[key] = pipeline;
    }
}


/**
 * Adds checkbox parameter
 * @param {object} parameters object
 * @param {string} checkboxName
 * @returns {boolean} form validation boolean
 */
function addCheckboxParameter(parameters, checkboxName) {

    var checkboxSelected = [];
    $("input:checkbox[name=" + checkboxName + "]:checked").each(function () {
        checkboxSelected.push($(this).val());
    });
    if ($.isEmptyObject(checkboxSelected)) {
        alert("Please select at least one network");
        return false
    } else {
        parameters[checkboxName] = checkboxSelected;
    }
    return true
}


$(document).ready(function () {


    $("#author_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type any authors",
        ajax: {
            url: function () {
                return "/api/authors/suggestion/";
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

    $("#pubmed_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type PubMed identifiers",
        ajax: {
            url: function () {
                return "/api/pubmed/suggestion/";
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

    $("#annotation_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type any annotation",
        ajax: {
            url: function () {
                return "/api/annotations/suggestion/";
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

    // Creates node multiselection input
    $("#node_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: 'Please type any node',
        ajax: {
            url: function (params) {
                return "/api/nodes/suggestion/";
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
                                id: item.id,
                                text: item.text
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
                    response(data);
                }
            });
        }, minLength: 2
    });


});

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
            new_field_group = container.children().filter('.form-inline:first-child').clone();
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





