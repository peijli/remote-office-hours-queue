import * as React from "react";
import { useState, useEffect } from "react";
import { Alert, Button, Form } from "react-bootstrap";
import PhoneInput from "react-phone-input-2";
import 'react-phone-input-2/lib/style.css'

import * as api from "../services/api";
import { MyUser } from "../models";
import { ErrorDisplay, FormError, checkForbiddenError, LoadingDisplay, LoginDialog, Breadcrumbs } from "./common";
import { usePromise } from "../hooks/usePromise";
import { redirectToLogin } from "../utils";
import { PageProps } from "./page";
import { validatePhoneNumber } from "../validation";

interface PreferencesEditorProps {
    user: MyUser;
    disabled: boolean;
    onUpdateInfo: (phoneNumber: string, notifyMeAttendee: boolean, notifyMeHost: boolean) => void;
    errorOccurred: boolean;
}

type ValidationStatus = null | Error[]; // null = no changes, [] = valid

function PreferencesEditor(props: PreferencesEditorProps) {
    const [phoneField, setPhoneField] = useState(props.user.phone_number);
    const [countryDialCode, setCountryDialCode] = useState("");
    const [notifyMeAttendee, setNotifyMeAttendee] = useState(props.user.notify_me_attendee);
    const [notifyMeHost, setNotifyMeHost] = useState(props.user.notify_me_host);
    const [validationStatus, setValidationStatus] = useState(undefined as undefined | ValidationStatus);

    const hasStartedEnteringPhoneNumber = phoneField.length > countryDialCode.length;
    const phoneNumberToSubmit = !hasStartedEnteringPhoneNumber ? "" : phoneField;
    const changed = props.user.phone_number !== phoneNumberToSubmit
        || props.user.notify_me_attendee !== notifyMeAttendee
        || props.user.notify_me_host !== notifyMeHost;

    const phoneInput = (
        <PhoneInput
            country={'us'}
            value={props.user.phone_number}
            onChange={(value: any, data: any) => {
                setPhoneField(value);
                if ('dialCode' in data) setCountryDialCode(data.dialCode);
            }}
            disabled={props.disabled}
            inputProps={{id: 'phone'}}
        />
    );
    const notifyMeAttendeeInput = (
        <Form.Check 
            type="checkbox"
            id="notify-me-attendee"
            disabled={!hasStartedEnteringPhoneNumber} 
            checked={notifyMeAttendee} 
            onChange={() => setNotifyMeAttendee(!notifyMeAttendee)}
            label="As an attendee, I want to be notified via SMS when it becomes my turn." />
    );
    const notifyMeHostInput = (
        <Form.Check 
            type="checkbox"
            id="notify-me-host"
            disabled={!hasStartedEnteringPhoneNumber} 
            checked={notifyMeHost}
            onChange={() => setNotifyMeHost(!notifyMeHost)}
            label="As a host, I want to be notified via SMS when someone joins my empty queue." />
    );

    const validateAndSubmit = (e: React.SyntheticEvent) => {
        e.preventDefault() // Prevent page reload
        if (!changed) {
            setValidationStatus(null);
            return;
        }
        if (!hasStartedEnteringPhoneNumber) {
            setValidationStatus([]);
            props.onUpdateInfo('', notifyMeAttendee, notifyMeHost);
            return; // Cleared form, so submit empty without validating
        }
        const validationErrors = validatePhoneNumber(phoneField, countryDialCode);
        setValidationStatus(validationErrors);
        if (!validationErrors.length)
            props.onUpdateInfo(phoneField, notifyMeAttendee, notifyMeHost);
    }

    const alertBlock =
        validationStatus === undefined // not yet validated
            ? undefined
        : validationStatus === null
            ? <Alert variant='primary'>Your preferences were not changed.</Alert>
        : validationStatus.length
            ? <Alert variant='danger'>{validationStatus.map(e => <p>{e.message}</p>)}</Alert>
        : props.errorOccurred
            ? <Alert variant='danger'>An error occurred while trying to update your preferences; please try again later.</Alert>
        : <Alert variant='success'>Your preferences were successfully updated.</Alert>

    return (
        <div>
            <h1>View/Update Preferences</h1>
            {alertBlock}
            <Form onSubmit={validateAndSubmit}>
                <p>Enter a phone number in order to opt in to SMS notifications.</p>
                <Form.Group controlId='phone'>
                    <Form.Label>Phone Number</Form.Label>
                    {phoneInput}
                    {notifyMeAttendeeInput}
                    {notifyMeHostInput}
                </Form.Group>
                <Button variant="primary" type="submit" disabled={props.disabled}>Save</Button>
            </Form>
        </div>
    );
}

export function PreferencesPage(props: PageProps) {
    if (!props.user) {
        redirectToLogin(props.loginUrl);
    }
    
    if (!props.user) throw new Error("user is undefined!");
    const userId = props.user.id

    // Setup basic state
    const [user, setUser] = useState(undefined as MyUser | undefined);
    const [doRefresh, refreshLoading, refreshError] = usePromise(() => api.getUser(userId) as Promise<MyUser>, setUser);
    useEffect(() => {
        doRefresh();
    }, []);

    // Setup interactions
    const [doUpdateInfo, updateInfoLoading, updateInfoError] = usePromise(
        (phoneNumber, notifyMeAttendee, notifyMeHost) =>
            api.updateProfile(userId, phoneNumber, notifyMeAttendee, notifyMeHost) as Promise<MyUser>, setUser
    );

    // Render
    const isChanging = updateInfoLoading;
    const isLoading = isChanging;
    const errorSources = [
        {source: 'Update Preferences', error: updateInfoError},
        {source: 'Load User', error: refreshError},
    ].filter(e => e.error) as FormError[];
    const loginDialogVisible = errorSources.some(checkForbiddenError);
    const loadingDisplay = <LoadingDisplay loading={isLoading}/>
    const errorDisplay = <ErrorDisplay formErrors={errorSources}/>
    const preferencesEditor = user
        && (
            <PreferencesEditor
                user={user}
                disabled={isChanging}
                onUpdateInfo={doUpdateInfo}
                errorOccurred={!!errorSources.length}
            />
        );
    return (
        <>
            <LoginDialog visible={loginDialogVisible} loginUrl={props.loginUrl} />
            <Breadcrumbs currentPageTitle='User Preferences' />
            {errorDisplay}
            {loadingDisplay}
            {preferencesEditor}
        </>
    );
}
