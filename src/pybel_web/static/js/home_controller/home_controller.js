/**
 * This JS file controls the QueryBuilder forms as well as autocompletions in network_list.html
 *
 * @summary   QueryBuilder of PyBEL explorer
 *
 * @requires jquery, select2
 *
 */

$(document).ready(function () {


    /**
     * Returns joined string with the properties of selection in a select2Element.
     * @param {select2} select2Element
     * @param {string} selectionProperty - text or id
     * @param {string} joinBy
     */
    function getSelection(select2Element, selectionProperty, joinBy) {

        var selectedElements = [];

        $.each(select2Element, function (index, value) {
            selectedElements.push(encodeURIComponent(value[selectionProperty]));
        });

        return selectedElements.join(joinBy)

    }

    /**
     * Populates hidden inputs in form (pubmed_list, author_list) with the selection from the select2Element.
     */
    $("#provenance_form").submit(function () {

        $("#pubmed_list").val(getSelection($("#pubmed_selection").select2("data"), "text", ","));

        $("#author_list").val(getSelection($("#author_selection").select2("data"), "text", ","));

    });


    /**
     * Populates hidden form (subgraph_form) with the selection from the select2Element.
     */
    $("#subgraph_form").submit(function () {

        $("#node_list").val(getSelection($("#node_selection").select2("data"), "id", ","));

    });

    $("#node_selection").select2({
        minimumInputLength: 2,
        multiple: true,
        placeholder: 'Please type your nodes of interest here',
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

    $("#author_selection").select2({
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type your authors of interest here",
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
                                id: item.id,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });

    $("#pubmed_selection").select2({
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type your PubMed identifiers of interest here",
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
                                id: item.id,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });
});
